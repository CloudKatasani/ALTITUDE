"""Server-rendered portal (Section 29 experience layer).

Pages are Jinja2 templates in ``portal/templates`` that use theme tokens only
(white-label); colours come from ``COLOR_*`` tokens injected as CSS variables.
Browser sessions authenticate with a bearer token cookie, or — in
``ALTITUDE_AUTH=dev`` mode — a role picker.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from altitude.core.paths import repo_root
from altitude.core.theme import render as render_tokens
from altitude.core.theme import tokens

from .auth import AuthError, Principal, authenticate, roles

PORTAL_DIR = repo_root() / "portal"

# Pages contributed by modules: (path, nav label, permission, handler(request, principal, ctx) -> (template, context))
PAGES: list[tuple[str, str, str, Any]] = []


def _env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(PORTAL_DIR / "templates")),
                      autoescape=select_autoescape(["html"]))
    env.filters["usd"] = lambda v: f"${float(v or 0):,.0f}"
    env.filters["pct"] = lambda v: f"{float(v or 0) * 100:.0f}%"
    return env


class _Headers(dict):
    def get(self, key: str, default: Any = None) -> Any:  # case-insensitive like Starlette headers
        return super().get(key.lower(), default)


def portal_principal(request: Request) -> Principal | None:
    hdrs = _Headers({k.lower(): v for k, v in request.headers.items()})
    tok = request.cookies.get("altitude_token")
    if tok:
        hdrs["authorization"] = f"Bearer {tok}"
    if os.environ.get("ALTITUDE_AUTH") == "dev" and request.cookies.get("altitude_role"):
        hdrs["x-altitude-user"] = request.cookies.get("altitude_user", "dev@local")
        hdrs["x-altitude-role"] = request.cookies["altitude_role"]
    try:
        return authenticate(hdrs)
    except AuthError:
        return None


def page(env: Environment, template: str, request: Request, p: Principal | None, **ctx: Any) -> HTMLResponse:
    nav = [(path, label) for path, label, perm, _ in PAGES if label and p and p.can(perm)]
    html = env.get_template(template).render(request=request, principal=p, nav=nav, theme=tokens(), **ctx)
    return HTMLResponse(render_tokens(html))


def mount(app: FastAPI) -> None:
    env = _env()
    static = PORTAL_DIR / "static"
    if static.exists():
        app.mount("/static", StaticFiles(directory=str(static)), name="static")
    ctx = app.state.ctx

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        from altitude.advisory import Sherpa

        from .routes.engagement import outcome_path

        engagements = ctx.store.query("SELECT * FROM engagement ORDER BY created_at")
        eng = engagements[0] if engagements else None
        phase = (eng or {}).get("current_phase") or "diagnose"
        facts = _facts(ctx, eng)
        sherpa = Sherpa(ctx.extras["grounding"](ctx))
        return page(env, "home.html", request, p, engagement=eng, engagements=engagements, path=outcome_path(),
                    phase=phase, actions=sherpa.next_actions(phase, facts), challenges=sherpa.challenges(facts))

    @app.get("/login", response_class=HTMLResponse)
    def login(request: Request) -> HTMLResponse:
        return page(env, "login.html", request, None, roles=roles(), dev=os.environ.get("ALTITUDE_AUTH") == "dev")

    @app.post("/login")
    def do_login(user: str = Form(""), role: str = Form(""), token: str = Form("")) -> RedirectResponse:
        resp = RedirectResponse("/", status_code=303)
        if token:
            resp.set_cookie("altitude_token", token, httponly=True, samesite="strict")
        elif os.environ.get("ALTITUDE_AUTH") == "dev" and role in roles():
            resp.set_cookie("altitude_user", user or "dev@local", httponly=True, samesite="strict")
            resp.set_cookie("altitude_role", role, httponly=True, samesite="strict")
        return resp

    @app.get("/logout")
    def logout() -> RedirectResponse:
        resp = RedirectResponse("/login", status_code=303)
        for c in ("altitude_token", "altitude_user", "altitude_role"):
            resp.delete_cookie(c)
        return resp

    @app.get("/review", response_class=HTMLResponse)
    def review(request: Request) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        from altitude.core.ai import ReviewQueue

        return page(env, "review.html", request, p, items=ReviewQueue(ctx.store).open_items())

    @app.post("/review/{item_id}")
    def review_decide(request: Request, item_id: str, decision: str = Form(...)) -> RedirectResponse:
        p = portal_principal(request)
        if p is None or not p.can("review"):
            return RedirectResponse("/login", status_code=303)
        from altitude.core import audit
        from altitude.core.ai import ReviewQueue

        ReviewQueue(ctx.store).decide(item_id, p.user, decision)
        audit.record(ctx.store, p.user, f"review.{decision}", subject_type="review_item", subject_id=item_id)
        return RedirectResponse("/review", status_code=303)

    def _engagement(engagement_id: str | None) -> dict | None:
        if engagement_id:
            return ctx.store.get("engagement", engagement_id=engagement_id)
        rows = ctx.store.query("SELECT * FROM engagement ORDER BY created_at LIMIT 1")
        return rows[0] if rows else None

    def _facts_page(request: Request, p: Principal, eng: dict | None, values: dict | None = None,
                    errors: dict | None = None, saved: list | None = None) -> HTMLResponse:
        from altitude.advisory import Sherpa
        from altitude.advisory.facts import catalogue

        from .routes.engagement import current_facts, fact_history

        current = current_facts(ctx.store, eng["engagement_id"]) if eng else {}
        history = fact_history(ctx.store, eng["engagement_id"]) if eng else {}
        shown = {**current, **(values or {})}
        challenges = Sherpa(ctx.extras["grounding"](ctx)).challenges(_facts(ctx, eng)) if eng else []
        engagements = ctx.store.query("SELECT engagement_id, name FROM engagement ORDER BY created_at")
        status = 422 if errors else 200
        resp = page(env, "facts.html", request, p, engagement=eng, engagements=engagements, groups=catalogue(),
                    values=shown, current=current, history=history, errors=errors or {}, saved=saved or [],
                    challenges=challenges, editable=p.can("run"))
        resp.status_code = status
        return resp

    @app.get("/facts", response_class=HTMLResponse)
    def facts_get(request: Request, engagement: str | None = None) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        saved = [k for k in request.query_params.get("saved", "").split(",") if k]
        return _facts_page(request, p, _engagement(engagement), saved=saved)

    @app.post("/facts", response_class=HTMLResponse)
    async def facts_post(request: Request) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        if not p.can("run"):
            return HTMLResponse("Forbidden: your role cannot edit engagement facts", status_code=403)
        from altitude.advisory.facts import parse

        from .routes.engagement import current_facts, write_facts

        form = await request.form()
        eng = _engagement(form.get("engagement_id"))
        if eng is None:
            return HTMLResponse("No such engagement", status_code=404)
        submitted = {k: v for k, v in form.items() if k != "engagement_id"}
        changes, errors = parse(submitted, current_facts(ctx.store, eng["engagement_id"]))
        if errors:
            return _facts_page(request, p, eng, values=submitted, errors=errors)
        if changes:
            write_facts(ctx.store, eng["engagement_id"], changes, p.user)
        return RedirectResponse(f"/facts?engagement={eng['engagement_id']}&saved={','.join(sorted(changes))}"
                                if changes else f"/facts?engagement={eng['engagement_id']}", status_code=303)

    @app.get("/sherpa", response_class=HTMLResponse)
    def sherpa_page(request: Request, q: str = "") -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        from altitude.advisory import Sherpa

        engs = ctx.store.query("SELECT * FROM engagement ORDER BY created_at LIMIT 1")
        answer = (Sherpa(ctx.extras["grounding"](ctx), store=ctx.store).ask(q, _facts(ctx, engs[0] if engs else None))
                  if q else None)
        return page(env, "sherpa.html", request, p, q=q, answer=answer)

    @app.get("/decisions", response_class=HTMLResponse)
    def decisions(request: Request) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        import json

        rows = ctx.store.query("SELECT * FROM decision ORDER BY decision_id")
        for r in rows:
            r["perspectives"] = json.loads(r["perspectives"]) if isinstance(r["perspectives"], str) else r["perspectives"]
        return page(env, "decisions.html", request, p, decisions=rows)

    for path, _label, perm, handler in PAGES:
        _register(app, env, ctx, path, perm, handler)
    for url, directory in ctx.extras.get("static_mounts", []):
        app.mount(url, StaticFiles(directory=str(directory), html=True), name=f"static:{url}")


def _register(app: FastAPI, env: Environment, ctx: Any, path: str, perm: str, handler: Any) -> None:
    @app.get(path, response_class=HTMLResponse, name=f"page:{path}")
    def _page(request: Request) -> HTMLResponse:
        p = portal_principal(request)
        if p is None:
            return RedirectResponse("/login", status_code=303)
        if not p.can(perm):
            return HTMLResponse("Forbidden", status_code=403)
        template, data = handler(request, p, ctx)
        return page(env, template, request, p, **data)


def _facts(ctx: Any, engagement: dict | None = None) -> dict:
    """Derived facts (review queue, snapshots, module providers) overlaid with facts recorded on the engagement."""
    facts: dict = {"review_items_open": len(ctx.store.query("SELECT 1 FROM review_item WHERE status='open'")),
                   "access_confirmed": True,
                   "snapshot_sealed": bool(ctx.store.query("SELECT 1 FROM snapshot LIMIT 1"))}
    for provider in ctx.extras.get("fact_providers", []):
        facts.update(provider(ctx))
    if engagement:
        from .routes.engagement import current_facts

        facts.update(current_facts(ctx.store, engagement["engagement_id"]))
    return facts


def register_page(path: str, label: str, permission: str, handler: Any) -> None:
    if all(p[0] != path for p in PAGES):
        PAGES.append((path, label, permission, handler))
