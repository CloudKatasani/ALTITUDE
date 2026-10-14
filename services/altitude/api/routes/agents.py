"""Agent fleet over the API and portal: catalogue, evals/promotion, runs, approvals and the immutable action log."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from altitude.core import audit
from altitude.core.errors import AltitudeError
from altitude.core.snapshot import Snapshot
from altitude.core.store import json_safe

from ..app import Context, get_ctx, require
from ..auth import Principal

router = APIRouter(prefix="/api/v1/agents")


class RunIn(BaseModel):
    snapshot_id: str
    tenant_id: str = "default"
    as_of: str | None = None
    simulate: bool = True


class DecisionIn(BaseModel):
    decision: str
    tenant_id: str = "default"
    comment: str | None = None


@router.get("")
def catalogue(p: Principal = Depends(require("read"))) -> list[dict]:
    from altitude_agents.catalogue import load_agent_catalogue

    return json_safe([{"agent_id": a.agent_id, "name": a.name, "max_autonomy": a.max_autonomy,
                       "implemented": a.implemented, "service_user": a.service_user}
                      for a in sorted(load_agent_catalogue().values(), key=lambda a: a.number)])


@router.post("/{agent_id}/evals")
def evals(agent_id: str, promote: bool = False, p: Principal = Depends(require("approve")),
          ctx: Context = Depends(get_ctx)) -> dict:
    from altitude_agents.errors import PromotionBlocked
    from altitude_agents.evals import promote as do_promote
    from altitude_agents.evals import run_suite

    rep = run_suite(agent_id)
    out = {"agent_id": agent_id, "version": rep.version, "passed": sum(c.passed for c in rep.cases),
           "cases": len(rep.cases), "failures": [{"case": c.case_id, "failures": c.failures} for c in rep.cases if not c.passed]}
    if promote:
        try:
            do_promote(ctx.store, rep, p.user)
            out["promoted"] = True
        except PromotionBlocked as e:
            raise HTTPException(409, str(e)) from None
    return out


@router.post("/{agent_id}/runs")
def run(agent_id: str, body: RunIn, p: Principal = Depends(require("run")), ctx: Context = Depends(get_ctx)) -> dict:
    from altitude_agents.executor import SimulatedSnowflake
    from altitude_agents.runtime import AgentRunner
    from altitude_agents.telemetry import Telemetry

    row = ctx.store.get("snapshot", snapshot_id=body.snapshot_id)
    if row is None:
        raise HTTPException(404, f"no snapshot {body.snapshot_id}")
    tel = Telemetry.open(row["location"])
    if body.as_of:
        tel = tel.at(body.as_of)
    executor = SimulatedSnowflake(tel) if body.simulate else None
    try:
        report = AgentRunner(ctx.store, tenant_id=body.tenant_id).run(agent_id, tel, trigger=f"api:{p.user}",
                                                                      executor=executor)
    except AltitudeError as e:
        raise HTTPException(409, str(e)) from None
    audit.record(ctx.store, p.user, "agents.run", subject_type="agent_run", subject_id=report.run_id)
    return report.to_dict()


@router.get("/actions")
def actions(status: str | None = None, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    rows = ctx.store.query(
        "SELECT * FROM agent_action a WHERE seq = (SELECT max(seq) FROM agent_action b WHERE b.action_id = a.action_id) "
        "ORDER BY recorded_at DESC")
    return json_safe([r for r in rows if not status or r["status"] == status])


@router.get("/actions/{action_id}")
def action_history(action_id: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    return json_safe(ctx.store.query("SELECT * FROM agent_action WHERE action_id = ? ORDER BY seq", [action_id]))


@router.post("/actions/{action_id}/decision")
def decide(action_id: str, body: DecisionIn, p: Principal = Depends(require("approve")),
           ctx: Context = Depends(get_ctx)) -> dict:
    from altitude_agents.actions import ActionGateway
    from altitude_agents.catalogue import load_tenant_policy

    gw = ActionGateway(ctx.store, load_tenant_policy(body.tenant_id))
    try:
        fn = gw.approve if body.decision == "approved" else gw.reject
        rec = fn(action_id, p.user, p.role, body.comment)
    except KeyError:
        raise HTTPException(404, f"no action {action_id}") from None
    except AltitudeError as e:
        raise HTTPException(403, str(e)) from None
    return json_safe({"action_id": rec.action_id, "status": rec.status, "approver": p.user})


def _agents_page(request: Request, p: Principal, ctx: Context):
    latest = ctx.store.query(
        "SELECT * FROM agent_action a WHERE seq = (SELECT max(seq) FROM agent_action b WHERE b.action_id = a.action_id) "
        "AND status = 'proposed' ORDER BY recorded_at DESC")
    # Only changes (L2 drafts, or L3 actions refused back to L2) need an approver; L0/L1 output is advice.
    pending = [a for a in latest if a["autonomy"] in ("L2", "L3") and a["action_type"] != "recommendation"]
    advice = [a for a in latest if a not in pending]
    recent = ctx.store.query("SELECT * FROM agent_action ORDER BY recorded_at DESC, seq DESC LIMIT 50")
    return "agents.html", {"pending": pending, "advice": advice, "recent": recent}


def init(ctx: Context) -> None:
    from .. import portal

    portal.register_page("/agents", "Agents", "read", _agents_page)
