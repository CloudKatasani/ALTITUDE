"""Package O over the API and portal: harvest, KPIs, reconciliation, alerts, dashboards, ask-the-platform, value loop."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from altitude.core import audit
from altitude.core.store import json_safe

from ..app import Context, get_ctx, require
from ..auth import Principal

router = APIRouter(prefix="/api/v1/observability")


def obs_db(ctx: Context):
    from altitude.observability.db import ObsDatabase

    if "obs_db" not in ctx.extras:
        path = Path(ctx.workspace) / "obs.duckdb"
        ctx.extras["obs_db"] = ObsDatabase(str(path))
    return ctx.extras["obs_db"]


class HarvestIn(BaseModel):
    as_of: date
    registry: dict[str, Any] | None = None
    days: int | None = None


class AskIn(BaseModel):
    question: str
    account: str | None = None


class AlertsIn(BaseModel):
    day: date | None = None
    registry: dict[str, Any] | None = None


class ValueIn(BaseModel):
    suggestions: list[dict[str, Any]] | None = None   # default: implemented Package D suggestions in the store
    implemented_at: dict[str, date] = {}              # suggestion id -> implementation date
    account: str | None = None
    baseline_health_index: float | None = None


@router.post("/harvest")
def harvest(body: HarvestIn, p: Principal = Depends(require("run")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    from altitude.observability.harvest import harvest_registry
    from altitude.observability.kpi import compute_kpis

    db = obs_db(ctx)
    results = harvest_registry(db, body.registry, body.as_of, days=body.days)
    compute_kpis(db)
    audit.record(ctx.store, p.user, "observability.harvest", details={"as_of": body.as_of.isoformat()})
    return json_safe([r.summary() for r in results])


@router.get("/kpis")
def kpis(p: Principal = Depends(require("read"))) -> list[dict]:
    from altitude.observability.kpi import implemented

    return json_safe([{k: v for k, v in kpi.items() if k != "sql"} for kpi in implemented()])


@router.get("/reconcile")
def reconcile(p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    from altitude.observability.reconcile import reconcile as rec

    r = rec(obs_db(ctx))
    return json_safe({"ok": r["ok"], "tolerance_pct": r["tolerance_pct"], "months": r["months"]})


@router.post("/ask")
def ask(body: AskIn, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    from altitude.observability.agent import AskThePlatform

    return json_safe(AskThePlatform(obs_db(ctx), store=ctx.store).ask(body.question, account=body.account).to_dict())


@router.post("/alerts/evaluate")
def alerts(body: AlertsIn, p: Principal = Depends(require("run")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    from altitude.observability.alerts import evaluate_alerts
    from altitude.observability.config import load_registry

    db = obs_db(ctx)
    day = body.day or db.scalar("SELECT max(PERIOD) FROM KPI.KPI_COST_011")
    events = evaluate_alerts(db, body.registry or load_registry(None), day, Path(ctx.workspace) / "outbox")
    return json_safe(events)


@router.post("/value")
def value(body: ValueIn, p: Principal = Depends(require("approve")), ctx: Context = Depends(get_ctx)) -> dict:
    """Suggestion-to-value loop: measure implemented suggestions' KPIs before/after and record realised value."""
    from altitude.observability.value import measure_suggestions, qbr_summary

    sugg = body.suggestions
    if sugg is None:
        sugg = []
        for r in ctx.store.query("SELECT record, status FROM diag_suggestion WHERE status = 'implemented'"):
            rec = json.loads(r["record"]) if isinstance(r["record"], str) else r["record"]
            rec["status"] = r["status"]
            if rec["id"] in body.implemented_at:
                rec["implemented_at"] = body.implemented_at[rec["id"]].isoformat()
            sugg.append(rec)
    db = obs_db(ctx)
    measured = measure_suggestions(db, sugg, store=ctx.store, account=body.account, actor=p.user)
    # mirror the realised status onto the Package D lifecycle
    for m in measured:
        if m.get("status") == "value_realised" and ctx.store.get("diag_suggestion", suggestion_id=m["id"]):
            from altitude.diagnostics import lifecycle

            if lifecycle.get(ctx.store, m["id"])["status"] == "implemented":
                lifecycle.transition(ctx.store, m["id"], "value_realised", actor=p.user, reviewer=p.user,
                                     comment="measured by Package O suggestion-to-value loop")
    qbr = qbr_summary(db, measured, account=body.account, baseline_health_index=body.baseline_health_index,
                      store=ctx.store)
    return json_safe({"suggestions": measured, "qbr": qbr})


@router.post("/dashboards")
def dashboards(p: Principal = Depends(require("run")), ctx: Context = Depends(get_ctx)) -> list[str]:
    from altitude.observability.dashboards import render_dashboards

    return render_dashboards(obs_db(ctx), Path(ctx.workspace) / "dashboards")


def _dashboard_page(request: Request, p: Principal, ctx: Context):
    base = Path(ctx.workspace) / "dashboards"
    files = sorted(str(f.relative_to(base)) for f in base.rglob("*.html")) if base.exists() else []
    return "dashboards.html", {"files": files}


def _grounding(ctx: Context) -> list:
    from altitude.advisory.grounding import GroundingDoc
    from altitude.observability.kpi import implemented

    return [GroundingDoc(k["id"], "kpi", k["name"], f"{k.get('definition', '')} domain {k.get('domain')}",
                         (str(k.get("domain")),)) for k in implemented()]


def init(ctx: Context) -> None:
    from fastapi.staticfiles import StaticFiles

    from .. import portal

    ctx.extras["grounding_providers"].append(_grounding)
    portal.register_page("/dashboards", "Observability", "read", _dashboard_page)
    base = Path(ctx.workspace) / "dashboards"
    base.mkdir(parents=True, exist_ok=True)
    ctx.extras["static_mounts"] = ctx.extras.get("static_mounts", []) + [("/dashboards/files", base)]
