"""FastAPI application: ``/api/v1`` REST API plus the server-rendered portal.

Every route authenticates (``altitude.api.auth``) and checks an RBAC permission
from ``knowledge/api/rbac.yaml``. State lives in the control-plane store
(``ALTITUDE_STORE``, DuckDB locally / PostgreSQL in SaaS) and the workspace
directory holding sealed snapshots and engagement artifacts
(``ALTITUDE_WORKSPACE``).
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from altitude import __version__
from altitude.core import audit
from altitude.core.ai import ReviewQueue
from altitude.core.knowledge import validate_tree
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store, json_safe
from altitude.core.theme import tokens

from .auth import AuthError, Principal, authenticate, roles

# Module routers mounted when the module is installed: each exposes ``router: APIRouter``.
ROUTER_MODULES = [
    "altitude.api.routes.engagement",
    "altitude.api.routes.diagnostics",
    "altitude.api.routes.observability",
    "altitude.api.routes.migration",
    "altitude.api.routes.agents",
    "altitude.api.routes.skills",
    "altitude.api.routes.website",
]


@dataclass
class Context:
    store: Store
    workspace: Path
    extras: dict[str, Any] = field(default_factory=dict)


def get_ctx(request: Request) -> Context:
    return request.app.state.ctx


def principal(request: Request) -> Principal:
    try:
        return authenticate(request.headers)
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None


def require(permission: str) -> Callable[[Principal], Principal]:
    def dep(p: Principal = Depends(principal)) -> Principal:
        if not p.can(permission):
            raise HTTPException(status_code=403, detail=f"role '{p.role}' lacks permission '{permission}'")
        return p

    return dep


class Decision(BaseModel):
    decision: str
    comment: str | None = None


class AskRequest(BaseModel):
    question: str
    facts: dict[str, Any] = {}


class BoardRequest(BaseModel):
    title: str
    facts: dict[str, Any]
    evidence_refs: list[str] = []
    engagement_id: str | None = None
    context: str = ""


def core_router() -> APIRouter:
    r = APIRouter(prefix="/api/v1")

    @r.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @r.get("/me")
    def me(p: Principal = Depends(principal)) -> dict:
        return {"user": p.user, "role": p.role, "tenant": p.tenant}

    @r.get("/roles")
    def list_roles(p: Principal = Depends(require("read"))) -> list[str]:
        return roles()

    @r.get("/theme")
    def theme() -> dict:
        return tokens()

    @r.get("/rubric")
    def rubric(ref: str | None = None, p: Principal = Depends(require("read"))) -> dict:
        rs = default_rubrics()
        return {"version": rs.version, "value": rs.get(ref) if ref else None}

    @r.get("/knowledge/problems")
    def knowledge_problems(p: Principal = Depends(require("read"))) -> dict:
        problems = validate_tree()
        return {"ok": not problems, "problems": problems}

    @r.get("/review-queue")
    def review_queue(subject_type: str | None = None, p: Principal = Depends(require("read")),
                     ctx: Context = Depends(get_ctx)) -> list[dict]:
        return json_safe(ReviewQueue(ctx.store).open_items(subject_type))

    @r.post("/review-queue/{item_id}/decision")
    def review_decide(item_id: str, body: Decision, p: Principal = Depends(require("review")),
                      ctx: Context = Depends(get_ctx)) -> dict:
        try:
            ReviewQueue(ctx.store).decide(item_id, p.user, body.decision, body.comment)
        except KeyError:
            raise HTTPException(404, f"no review item {item_id}") from None
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        audit.record(ctx.store, p.user, f"review.{body.decision}", subject_type="review_item", subject_id=item_id)
        return {"item_id": item_id, "decision": body.decision, "reviewer": p.user}

    @r.get("/audit")
    def audit_events(subject_type: str | None = None, subject_id: str | None = None, limit: int = 200,  # threshold-ok: page size
                     p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
        if subject_type and subject_id:
            return json_safe(audit.trail(ctx.store, subject_type, subject_id))
        return json_safe(ctx.store.query("SELECT * FROM audit_event ORDER BY occurred_at DESC LIMIT ?", [limit]))

    @r.get("/snapshots")
    def snapshots(p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
        rows = ctx.store.query("SELECT snapshot_id, kind, content_hash, engagement_id, sealed_at FROM snapshot "
                               "ORDER BY sealed_at DESC")
        return json_safe(rows)

    @r.post("/sherpa/ask")
    def sherpa_ask(body: AskRequest, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
        from altitude.advisory import Sherpa

        return Sherpa(ctx.extras["grounding"](ctx), store=ctx.store).ask(body.question, body.facts).to_dict()

    @r.get("/advisors")
    def advisors(p: Principal = Depends(require("read"))) -> list[dict]:
        from altitude.core.knowledge import load_yaml

        return load_yaml("advisory/advisors.yaml")["advisors"]

    @r.post("/advisors/{advisor_id}/ask")
    def advisor_ask(advisor_id: str, body: AskRequest, p: Principal = Depends(require("read")),
                    ctx: Context = Depends(get_ctx)) -> dict:
        from altitude.advisory import Sherpa

        try:
            s = Sherpa.advisor(advisor_id, ctx.extras["grounding"](ctx), store=ctx.store)
        except KeyError:
            raise HTTPException(404, f"no advisor {advisor_id}") from None
        return s.ask(body.question, body.facts).to_dict()

    @r.post("/review-board")
    def review_board(body: BoardRequest, p: Principal = Depends(require("run")),
                     ctx: Context = Depends(get_ctx)) -> dict:
        from altitude.advisory import ReviewBoard

        res = ReviewBoard(store=ctx.store).review(body.title, body.facts, body.evidence_refs, body.engagement_id,
                                                  body.context)
        audit.record(ctx.store, p.user, "review_board.review", subject_type="decision", subject_id=res.decision_id)
        return res.to_dict()

    @r.post("/review-board/{decision_id}/decision")
    def review_board_decide(decision_id: str, body: Decision, p: Principal = Depends(require("decide:board")),
                            ctx: Context = Depends(get_ctx)) -> dict:
        from altitude.advisory import ReviewBoard

        if not ctx.store.get("decision", decision_id=decision_id):
            raise HTTPException(404, f"no decision {decision_id}")
        ReviewBoard(store=ctx.store).decide(decision_id, p.user, body.decision == "accepted")
        return {"decision_id": decision_id, "status": body.decision}

    return r


def default_grounding(ctx: Context):
    """Grounding index for Sherpa: Pattern Library plus whatever modules contribute via ``ctx.extras``."""
    from altitude.advisory.sherpa import build_index

    docs = []
    for provider in ctx.extras.get("grounding_providers", []):
        docs.extend(provider(ctx))
    return build_index(extra=docs)


def create_app(store: Store | None = None, workspace: str | Path | None = None) -> FastAPI:
    workspace = Path(workspace or os.environ.get("ALTITUDE_WORKSPACE", ".altitude"))
    workspace.mkdir(parents=True, exist_ok=True)
    if store is None:
        store = Store(os.environ.get("ALTITUDE_STORE", str(workspace / "control.duckdb")))
    app = FastAPI(title=tokens()["PRODUCT_NAME"] + " API", version=__version__,
                  description="Evidence-first Snowflake diagnostics, observability, migration and run platform.")
    app.state.ctx = Context(store=store, workspace=workspace,
                            extras={"grounding": default_grounding, "grounding_providers": []})

    @app.exception_handler(AuthError)
    async def _auth_error(request: Request, exc: AuthError) -> JSONResponse:  # pragma: no cover - defensive
        return JSONResponse(status_code=401, content={"detail": str(exc)})

    app.include_router(core_router())
    for name in ROUTER_MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name and name.startswith(e.name):
                continue
            raise
        app.include_router(mod.router)
        if hasattr(mod, "init"):
            mod.init(app.state.ctx)
    try:
        from altitude.api import portal

        portal.mount(app)
    except ModuleNotFoundError as e:  # pragma: no cover
        if not (e.name and "portal" in e.name):
            raise
    return app
