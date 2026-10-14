"""``/api/v1/skills`` — list and invoke executable skills (same registry as the MCP server)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from altitude.core import audit
from altitude.core.store import json_safe
from altitude.skills import SkillError, load_skills, run_skill

from ..app import Context, get_ctx, principal
from ..auth import Principal

router = APIRouter(prefix="/api/v1")


@router.get("/skills")
def list_skills(p: Principal = Depends(principal)) -> list[dict]:
    return [{**s.tool_spec(), "permission": s.permission, "available": s.available} for s in load_skills().values()]


@router.post("/skills/{name}")
def call_skill(name: str, arguments: dict[str, Any] | None = None, p: Principal = Depends(principal),
               ctx: Context = Depends(get_ctx)) -> Any:
    try:
        out = run_skill(name, arguments or {}, context=ctx, principal=p)
    except SkillError as e:
        code = 403 if "lacks permission" in str(e) else (404 if "unknown skill" in str(e) else 422)
        raise HTTPException(code, str(e)) from None
    audit.record(ctx.store, p.user, f"skill.{name}", subject_type="skill", subject_id=name)
    return json_safe(out)
