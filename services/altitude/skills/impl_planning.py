"""Skill adapters for planning & estimation (``altitude.planning``)."""

from __future__ import annotations

import fnmatch
import json
from typing import Any

from .context import coerce
from .impl_common import out_dir, resolve_snapshot_path, safe
from .registry import SkillError


def _planning_context(ctx: Any, assessment_snapshot_id: str | None, harvest_snapshot_id: str | None,
                      inputs: dict | None):
    """PlanningContext from an assessment snapshot (or a harvest snapshot, assessed on demand)."""
    from altitude.core.errors import AltitudeError
    from altitude.planning import PlanningContext

    if assessment_snapshot_id:
        assessment: Any = str(resolve_snapshot_path(ctx, assessment_snapshot_id))
    elif harvest_snapshot_id:
        from .impl_assessment import _assessment

        assessment = _assessment(ctx, harvest_snapshot_id)
    else:
        raise SkillError("one of assessment_snapshot_id or harvest_snapshot_id is required")
    try:
        return PlanningContext.load(assessment, None, store=ctx.store, inputs=inputs or {})
    except AltitudeError as e:
        raise SkillError(str(e)) from None


def _select(pctx: Any, object_ids: list | None, names: list | None) -> list[str] | None:
    if not object_ids and not names:
        return None
    ids = set(object_ids or [])
    unknown = sorted(ids - set(pctx.objects))
    if unknown:
        raise SkillError(f"unknown object ids: {unknown}")
    for pattern in names or []:
        ids |= {oid for oid, o in pctx.objects.items() if fnmatch.fnmatch(o.fq_name.lower(), pattern.lower())}
    if not ids:
        raise SkillError("no objects match the given names")
    return sorted(ids)


def recommend_pattern(context: Any = None, assessment_snapshot_id: str | None = None,
                      harvest_snapshot_id: str | None = None, inputs: dict | None = None,
                      object_ids: list | None = None, names: list | None = None) -> dict:
    """Migration pattern recommendation (programme, or a set of objects) with confidence, rationale and dissent."""
    from altitude.planning import evidence_inputs, recommend

    ctx = coerce(context)
    pctx = _planning_context(ctx, assessment_snapshot_id, harvest_snapshot_id, inputs)
    ids = _select(pctx, object_ids, names)
    scope = "programme" if ids is None else "objects"
    merged = {**pctx.inputs, **evidence_inputs(pctx, ids if ids is not None else pctx.in_scope())}
    rec = recommend(merged, scope=scope, snapshot_id=pctx.snapshot_id, rubrics=ctx.rubrics)
    return safe({**rec.to_dict(), "object_count": len(ids if ids is not None else pctx.in_scope())})


def plan_waves(context: Any = None, assessment_snapshot_id: str | None = None,
               harvest_snapshot_id: str | None = None, inputs: dict | None = None, record: bool = True) -> dict:
    """Cluster in-scope objects into migration waves under the wave rules; record the plan and estimates."""
    from altitude.planning import WavePlanner, record_plan

    ctx = coerce(context)
    pctx = _planning_context(ctx, assessment_snapshot_id, harvest_snapshot_id, inputs)
    plan = WavePlanner(pctx, rubrics=ctx.rubrics, store=ctx.store).plan()
    if record:
        record_plan(ctx.store, plan, pctx)
    path = out_dir(ctx, "plan_waves") / f"{plan.plan_id}.json"
    path.write_text(json.dumps(safe(plan.to_dict()), indent=2, sort_keys=True, default=str) + "\n")
    return safe({
        "plan_id": plan.plan_id, "status": plan.status, "status_reasons": plan.status_reasons,
        "snapshot_id": plan.snapshot_id, "harvest_snapshot_id": plan.harvest_snapshot_id,
        "rubric_version": plan.rubric_version, "rules_version": plan.rules_version, "start_date": plan.start_date,
        "waves": [{"wave": w.ordinal, "wave_id": w.wave_id, "name": w.name, "objects": len(w.object_ids),
                   "weeks": w.weeks, "hours_p50": w.hours_p50, "start": w.start_date, "cutover": w.cutover_date,
                   "pattern": w.pattern, "thin_slice": w.thin_slice} for w in plan.waves],
        "decommission": len(plan.decommission), "violations": plan.violations,
        "p50_hours": plan.programme_estimate["p50_hours"], "p80_hours": plan.programme_estimate["p80_hours"],
        "programme_pattern": plan.programme_recommendation.get("pattern"), "plan_path": str(path),
        "recorded": record,
    })


def estimate_wave(context: Any = None, assessment_snapshot_id: str | None = None,
                  harvest_snapshot_id: str | None = None, inputs: dict | None = None, wave: int | None = None,
                  object_ids: list | None = None, names: list | None = None, cutovers: int = 1,
                  record: bool = True) -> dict:
    """p50/p80 effort estimate with confidence and factors for a planned wave, a set of objects, or the programme."""
    from altitude.planning import Estimator, WavePlanner, record_estimate

    ctx = coerce(context)
    pctx = _planning_context(ctx, assessment_snapshot_id, harvest_snapshot_id, inputs)
    est = Estimator(pctx, ctx.rubrics)
    if wave is not None:
        plan = WavePlanner(pctx, rubrics=ctx.rubrics, store=ctx.store).plan()
        match = next((w for w in plan.waves if w.ordinal == wave), None)
        if match is None:
            raise SkillError(f"plan {plan.plan_id} has no wave {wave} (waves: {[w.ordinal for w in plan.waves]})")
        result = est.estimate(match.wave_id, match.object_ids, cutovers=cutovers)
        extra = {"plan_id": plan.plan_id, "wave": wave, "wave_name": match.name}
    else:
        ids = _select(pctx, object_ids, names)
        if ids is None:
            result = est.estimate("programme", None, include_foundation=True, include_retired=True, cutovers=cutovers)
        else:
            result = est.estimate("objects", ids, cutovers=cutovers)
        extra = {}
    if record:
        record_estimate(ctx.store, result)
    d = result.to_dict()
    return safe({**{k: d[k] for k in ("estimate_id", "scope", "snapshot_id", "harvest_snapshot_id", "rubric_version",
                                      "p50_hours", "p80_hours", "confidence", "rationale", "object_count",
                                      "confidence_components")},
                 "factors": d["factors"], **extra, "recorded": record})
