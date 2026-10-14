"""Package D over the API and portal: runs, suggestions with evidence drill-through, lifecycle, exports,
and the progress board (every number links to evidence or suggestion IDs)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from altitude.core import audit
from altitude.core.errors import AltitudeError
from altitude.core.snapshot import Snapshot
from altitude.core.store import json_safe

from ..app import Context, get_ctx, require
from ..auth import Principal

router = APIRouter(prefix="/api/v1/diagnostics")


class RunIn(BaseModel):
    snapshot_id: str
    tier: str = "D2"
    engagement_id: str | None = None
    tenant_id: str | None = None


class TransitionIn(BaseModel):
    to_status: str
    comment: str | None = None


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v


def _snapshot(ctx: Context, snapshot_id: str) -> Snapshot:
    row = ctx.store.get("snapshot", snapshot_id=snapshot_id)
    if row is None:
        raise HTTPException(404, f"no snapshot {snapshot_id}")
    return Snapshot.open(row["location"])


def run_diagnostic(ctx: Context, snapshot_id: str, tier: str = "D2", engagement_id: str | None = None,
                   tenant_id: str | None = None, actor: str = "system") -> dict:
    from altitude.diagnostics import lifecycle
    from altitude.diagnostics.engine import run
    from altitude.diagnostics.exports import export_all

    snap = _snapshot(ctx, snapshot_id)
    result = run(snap, tier=tier)
    rid = lifecycle.persist(result, ctx.store, tenant_id=tenant_id, engagement_id=engagement_id, snapshot=snap)
    out = Path(ctx.workspace) / "diagnostics" / rid
    files = export_all(result, out, recs=lifecycle.overlay_status(result, ctx.store))
    audit.record(ctx.store, actor, "diagnostics.run", subject_type="diag_run", subject_id=rid,
                 details={"snapshot_id": snapshot_id, "tier": tier})
    return {"run_id": rid, **result.stamp, "platform_health_index": result.scorecard["platform_health_index"],
            "suggestions": len(result.details), "exports": sorted(p.name for p in files.values())}


@router.post("/runs")
def post_run(body: RunIn, p: Principal = Depends(require("run")), ctx: Context = Depends(get_ctx)) -> dict:
    return run_diagnostic(ctx, body.snapshot_id, body.tier, body.engagement_id, body.tenant_id or p.tenant, p.user)


@router.get("/runs")
def list_runs(p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    rows = ctx.store.query("SELECT run_id, snapshot_id, rubric_version, tier, platform_health_index, suggestions, "
                           "created_at FROM diag_run ORDER BY created_at DESC")
    return json_safe(rows)


@router.get("/runs/{run_id}")
def get_run(run_id: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    row = ctx.store.get("diag_run", run_id=run_id)
    if row is None:
        raise HTTPException(404, f"no run {run_id}")
    row["summary"] = _j(row["summary"])
    row["scores"] = ctx.store.all("diag_score", run_id=run_id)
    return json_safe(row)


@router.get("/runs/{run_id}/exports/{name}")
def get_export(run_id: str, name: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)):
    base = (Path(ctx.workspace) / "diagnostics" / run_id).resolve()
    path = (base / name).resolve()
    if base not in path.parents or not path.is_file():
        raise HTTPException(404, "no such export")
    return FileResponse(path)


def suggestion_detail(ctx: Context, suggestion_id: str) -> dict:
    from altitude.diagnostics import lifecycle

    row = ctx.store.get("diag_suggestion", suggestion_id=suggestion_id)
    if row is None:
        raise HTTPException(404, f"no suggestion {suggestion_id}")
    rec = _j(row["record"])
    rec.update(status=row["status"], reviewer=row["reviewer"])
    evidence = [dict(e, metrics=_j(e["metrics"])) for e in ctx.store.query(
        "SELECT * FROM diag_evidence WHERE evidence_id IN (SELECT unnest(?::VARCHAR[]))", [rec["evidence_refs"]])]
    return json_safe({"suggestion": rec, "narrative": row["narrative"], "needs_review": row["needs_review"],
                      "evidence": evidence, "history": lifecycle.history(ctx.store, suggestion_id)})


@router.get("/suggestions")
def list_suggestions(snapshot_id: str | None = None, p: Principal = Depends(require("read")),
                     ctx: Context = Depends(get_ctx)) -> list[dict]:
    from altitude.diagnostics import lifecycle

    return json_safe(lifecycle.statuses(ctx.store, snapshot_id))


@router.get("/suggestions/{suggestion_id}")
def get_suggestion(suggestion_id: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    return suggestion_detail(ctx, suggestion_id)


@router.post("/suggestions/{suggestion_id}/transition")
def transition(suggestion_id: str, body: TransitionIn, p: Principal = Depends(require("review")),
               ctx: Context = Depends(get_ctx)) -> dict:
    from altitude.diagnostics import lifecycle

    if body.to_status in ("accepted", "rejected", "value_realised") and not p.can("approve"):
        raise HTTPException(403, f"role '{p.role}' cannot move a suggestion to {body.to_status}")
    try:
        row = lifecycle.transition(ctx.store, suggestion_id, body.to_status, actor=p.user, reviewer=p.user,
                                   comment=body.comment)
    except KeyError:
        raise HTTPException(404, f"no suggestion {suggestion_id}") from None
    except (AltitudeError, ValueError) as e:
        raise HTTPException(409, str(e)) from None
    return json_safe(row)


@router.get("/evidence/{evidence_id}")
def get_evidence(evidence_id: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    row = ctx.store.get("diag_evidence", evidence_id=evidence_id)
    if row is None:
        raise HTTPException(404, f"no evidence {evidence_id}")
    row["metrics"] = _j(row["metrics"])
    row["suggestions"] = [r["suggestion_id"] for r in ctx.store.query(
        "SELECT suggestion_id FROM diag_suggestion WHERE list_contains(CAST(json_extract(record, '$.evidence_refs') "
        "AS VARCHAR[]), ?)", [evidence_id])]
    return json_safe(row)


# --------------------------------------------------------------------------- progress board


def progress_board(ctx: Context) -> dict:
    """Identified vs realised value; every number carries the IDs it was computed from."""
    rows = ctx.store.query("SELECT suggestion_id, status, quadrant, value_p50_usd, record FROM diag_suggestion")
    by_status: dict[str, dict] = {}
    for r in rows:
        b = by_status.setdefault(r["status"], {"count": 0, "value_p50_usd": 0.0, "ids": []})
        b["count"] += 1
        b["value_p50_usd"] += float(r["value_p50_usd"] or 0)
        b["ids"].append(r["suggestion_id"])
    realised = []
    try:
        realised = ctx.store.query("SELECT * FROM obs_value_measurement ORDER BY measured_at")
    except Exception:  # noqa: BLE001 - observability module tables absent
        realised = []
    realised = [m for m in realised if m.get("outcome") == "value_realised"]
    realised_usd = sum(float(m.get("realised_usd") or 0) for m in realised)
    quick = [r for r in rows if r["quadrant"] == "quick_win"]
    return json_safe({
        "identified": {"count": len(rows), "value_p50_usd": round(sum(float(r["value_p50_usd"] or 0) for r in rows), 2),
                       "ids": sorted(r["suggestion_id"] for r in rows)},
        "by_status": by_status,
        "quick_wins": {"count": len(quick), "ids": sorted(r["suggestion_id"] for r in quick)},
        "realised": {"value_annual_usd": round(realised_usd, 2),
                     "ids": [m["measurement_id"] for m in realised],
                     "suggestion_ids": sorted({m["suggestion_id"] for m in realised})},
    })


@router.get("/progress")
def get_progress(p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    return progress_board(ctx)


# --------------------------------------------------------------------------- integration hooks


def _grounding(ctx: Context) -> list:
    from altitude.advisory.grounding import GroundingDoc, docs_from_suggestions

    recs = []
    for r in ctx.store.query("SELECT record, status FROM diag_suggestion"):
        rec = _j(r["record"])
        rec["status"] = r["status"]
        recs.append(rec)
    docs = docs_from_suggestions(recs)
    for e in ctx.store.query("SELECT evidence_id, check_id, object_name, kind, metrics FROM diag_evidence"):
        docs.append(GroundingDoc(e["evidence_id"], "evidence", f"{e['check_id']} evidence on {e['object_name']}",
                                 f"{e['kind']} {e['object_name']} {e['check_id']} metrics {e['metrics']}"))
    return docs


def _facts(ctx: Context) -> dict:
    rows = ctx.store.query("SELECT status, quadrant FROM diag_suggestion")
    return {"quick_wins_open": sum(1 for r in rows if r["quadrant"] == "quick_win" and r["status"] in ("proposed", "accepted")),
            "quick_wins_implemented": sum(1 for r in rows if r["quadrant"] == "quick_win"
                                          and r["status"] in ("implemented", "value_realised"))}


def _findings_page(request: Request, p: Principal, ctx: Context):
    from altitude.diagnostics import lifecycle

    run = ctx.store.query("SELECT * FROM diag_run ORDER BY created_at DESC LIMIT 1")
    rows = ctx.store.query("SELECT suggestion_id, check_id, title, status, quadrant, priority_rank, value_p50_usd, "
                           "confidence, needs_review, record FROM diag_suggestion ORDER BY priority_rank")
    for r in rows:
        r["record"] = _j(r["record"])
    run = run[0] if run else None
    if run:
        run["summary"] = _j(run["summary"])
    return "findings.html", {"run": run, "rows": rows, "statuses": lifecycle}


def _suggestion_page(request: Request, p: Principal, ctx: Context):
    sid = request.query_params.get("id", "")
    return "suggestion.html", {"d": suggestion_detail(ctx, sid)}


def _progress_page(request: Request, p: Principal, ctx: Context):
    return "progress.html", {"b": progress_board(ctx)}


def init(ctx: Context) -> None:
    from .. import portal

    ctx.extras["grounding_providers"].append(_grounding)
    ctx.extras.setdefault("fact_providers", []).append(_facts)
    portal.register_page("/findings", "Findings", "read", _findings_page)
    portal.register_page("/suggestion", "", "read", _suggestion_page)
    portal.register_page("/progress", "Progress", "read", _progress_page)
