"""Tenants, clients and engagements; the guided outcome path."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from altitude.core import audit
from altitude.core.ids import stable_id
from altitude.core.knowledge import load_yaml
from altitude.core.store import json_safe

from ..app import Context, get_ctx, require
from ..auth import Principal

router = APIRouter(prefix="/api/v1")


class EngagementIn(BaseModel):
    tenant: str
    client: str
    package: str
    name: str
    industry: str | None = None


class PhaseIn(BaseModel):
    phase: str


class FactsIn(BaseModel):
    facts: dict


def current_facts(store, engagement_id: str) -> dict:
    """Latest value per fact key for an engagement."""
    import json

    rows = store.query("SELECT fact_key, value FROM engagement_fact WHERE engagement_id = ? ORDER BY set_at",
                       [engagement_id])
    out = {}
    for r in rows:
        v = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]
        out[r["fact_key"]] = v["v"] if isinstance(v, dict) and "v" in v else v
    return out


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def outcome_path() -> list[dict]:
    return load_yaml("advisory/outcome_path.yaml")["phases"]


@router.get("/outcome-path")
def get_outcome_path(p: Principal = Depends(require("read"))) -> list[dict]:
    return outcome_path()


@router.get("/engagements")
def list_engagements(p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> list[dict]:
    return json_safe(ctx.store.query("SELECT * FROM engagement ORDER BY created_at"))


@router.post("/engagements")
def create_engagement(body: EngagementIn, p: Principal = Depends(require("admin:engagement")),
                      ctx: Context = Depends(get_ctx)) -> dict:
    return create(ctx, body.tenant, body.client, body.package, body.name, body.industry, actor=p.user)


def create(ctx: Context, tenant: str, client: str, package: str, name: str, industry: str | None = None,
           actor: str = "system") -> dict:
    tid = stable_id("TEN", tenant)
    cid = stable_id("CLI", tenant, client)
    eid = stable_id("ENG", tenant, client, name)
    if not ctx.store.get("tenant", tenant_id=tid):
        ctx.store.insert("tenant", {"tenant_id": tid, "name": tenant, "created_at": _now()})
    if not ctx.store.get("client", client_id=cid):
        ctx.store.insert("client", {"client_id": cid, "tenant_id": tid, "name": client, "industry": industry,
                                    "created_at": _now()})
    if not ctx.store.get("engagement", engagement_id=eid):
        ctx.store.insert("engagement", {"engagement_id": eid, "tenant_id": tid, "client_id": cid, "package": package,
                                        "name": name, "current_phase": outcome_path()[0]["id"], "status": "active",
                                        "created_at": _now()})
        audit.record(ctx.store, actor, "engagement.create", subject_type="engagement", subject_id=eid, tenant_id=tid)
    return json_safe(ctx.store.get("engagement", engagement_id=eid))


@router.post("/engagements/{engagement_id}/phase")
def set_phase(engagement_id: str, body: PhaseIn, p: Principal = Depends(require("decide:gate")),
              ctx: Context = Depends(get_ctx)) -> dict:
    if body.phase not in {ph["id"] for ph in outcome_path()}:
        raise HTTPException(422, f"unknown phase {body.phase}")
    if not ctx.store.get("engagement", engagement_id=engagement_id):
        raise HTTPException(404, f"no engagement {engagement_id}")
    ctx.store.update("engagement", {"engagement_id": engagement_id}, {"current_phase": body.phase})
    audit.record(ctx.store, p.user, "engagement.phase", subject_type="engagement", subject_id=engagement_id,
                 details={"phase": body.phase})
    return json_safe(ctx.store.get("engagement", engagement_id=engagement_id))


@router.get("/engagements/{engagement_id}/facts")
def get_facts(engagement_id: str, p: Principal = Depends(require("read")), ctx: Context = Depends(get_ctx)) -> dict:
    return json_safe(current_facts(ctx.store, engagement_id))


@router.put("/engagements/{engagement_id}/facts")
def put_facts(engagement_id: str, body: FactsIn, p: Principal = Depends(require("run")),
              ctx: Context = Depends(get_ctx)) -> dict:
    if not ctx.store.get("engagement", engagement_id=engagement_id):
        raise HTTPException(404, f"no engagement {engagement_id}")
    now = _now()
    ctx.store.insert("engagement_fact", [{"engagement_id": engagement_id, "fact_key": k, "value": {"v": v},
                                          "set_by": p.user, "set_at": now} for k, v in sorted(body.facts.items())])
    audit.record(ctx.store, p.user, "engagement.facts", subject_type="engagement", subject_id=engagement_id,
                 details={"keys": sorted(body.facts)})
    return json_safe(current_facts(ctx.store, engagement_id))
