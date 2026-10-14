"""Estimation engine (Section 32): evidence x factors from ``rubric.estimation``.

An estimate is p50/p80 hours with a confidence computed from data completeness
and a rationale listing every factor. It references the ``rubric_version`` and
the assessment ``snapshot_id`` it was computed from; the same inputs always
reproduce the same estimate (no wall-clock or random values in the result).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from altitude.core.ids import canonical_json, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .context import PROCEDURAL_TYPES, PlanningContext

R = "rubric.estimation."


@dataclass
class Estimate:
    estimate_id: str
    scope: str
    engagement_id: str | None
    snapshot_id: str
    harvest_snapshot_id: str
    rubric_version: str
    p50_hours: float
    p80_hours: float
    confidence: float
    rationale: str
    object_count: int
    factors: list[dict[str, Any]] = field(default_factory=list)
    confidence_components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def weeks(self, team_hours_per_week: float) -> int:
        return max(1, math.ceil(self.p50_hours / team_hours_per_week))


def _r2(x: float) -> float:
    return round(x + 0.0, 2)


class Estimator:
    def __init__(self, ctx: PlanningContext, rubrics: RubricSet | None = None):
        self.ctx = ctx
        self.rubrics = rubrics or default_rubrics()

    def g(self, path: str) -> Any:
        return self.rubrics.get(R + path)

    # ------------------------------------------------------------------ per-object factor
    def object_factor(self, oid: str) -> tuple[str, float, float]:
        """(factor key, quantity, unit hours) for converting one in-scope object."""
        o = self.ctx.objects[oid]
        unit = self.g("unit_effort_hours")
        per100 = max(o.loc, 1) / 100
        if o.object_type == "table":
            return "table_ddl", 1.0, float(unit["table_ddl"])
        if o.object_type == "view":
            key = "view_complex" if o.band in self.g("view_complex_bands") else "view_simple"
            return key, 1.0, float(unit[key])
        if o.object_type == "script":
            return f"bteq_script_per_100_loc.{o.band}", per100, float(unit["bteq_script_per_100_loc"][o.band])
        if o.object_type == "etl_job":
            cls = self.g("etl_job_class_by_band")[o.band]
            return f"etl_job.{cls}", 1.0, float(unit["etl_job"][cls])
        if o.object_type == "report":
            return "report.repoint", 1.0, float(unit["report"]["repoint"])
        if o.object_type == "schedule":
            return "schedule", 1.0, float(unit["schedule"])
        return f"procedure_per_100_loc.{o.band}", per100, float(unit["procedure_per_100_loc"][o.band])

    def object_hours(self, oid: str) -> float:
        _, qty, unit = self.object_factor(oid)
        return qty * unit

    # ------------------------------------------------------------------ confidence
    def confidence_components(self, ids: list[str]) -> dict[str, float]:
        ctx = self.ctx
        conf = self.g("confidence")
        history = ctx.estate.history_days or 0
        code = [i for i in ids if ctx.objects[i].object_type not in {"table"}]
        with_text = [i for i in code if ctx.objects[i].loc > 0]
        unresolved = [i for i in code if ctx.objects[i].attrs.get("unresolved_refs") not in (None, "[]")]
        reviewed = [i for i in ids if not ctx.objects[i].needs_review]
        wanted = conf["programme_inputs"]
        provided = [k for k in wanted if ctx.inputs.get(k) is not None]
        return {
            "usage_history": round(min(1.0, history / float(conf["usage_history_full_days"])), 3),
            "code_coverage": round(len(with_text) / len(code), 3) if code else 1.0,
            "dependency_coverage": round(1 - len(unresolved) / len(code), 3) if code else 1.0,
            "classification": round(len(reviewed) / len(ids), 3) if ids else 1.0,
            "programme_inputs": round(len(provided) / len(wanted), 3) if wanted else 1.0,
        }

    # ------------------------------------------------------------------ estimate
    def estimate(self, scope: str, object_ids: Iterable[str] | None = None, *, include_foundation: bool = False,
                 include_retired: bool = False, cutovers: int = 1) -> Estimate:
        ctx = self.ctx
        ids = sorted(object_ids) if object_ids is not None else ctx.in_scope()
        convert = [i for i in ids if ctx.objects[i].disposition != "retire"]
        factors: dict[str, dict[str, Any]] = {}

        def add(name: str, qty: float, unit: float) -> float:
            f = factors.setdefault(name, {"factor": name, "quantity": 0.0, "unit_hours": unit, "hours": 0.0})
            f["quantity"] = round(f["quantity"] + qty, 4)
            f["hours"] = _r2(f["quantity"] * unit)
            return qty * unit

        for oid in convert:
            add(*self.object_factor(oid))
        base = sum(f["hours"] for f in factors.values())
        notes = [f"{len(convert)} objects to convert ({self._mix(convert)}): {base:.2f}h base from "
                 f"{len(factors)} factors (largest: {self._largest(factors)})"]

        s1 = sum(ctx.objects[i].s1_issues for i in convert)
        if s1:
            add("s1_issue_density", float(s1), float(self.g("multipliers.s1_issue_density.per_issue")))
            notes.append(f"{s1} S1 semantic-drift occurrences")
        subtotal = sum(f["hours"] for f in factors.values())

        mult = self.g("multipliers")
        uplift = 0.0
        if ctx.inputs.get("test_coverage") is not True:
            k = float(mult["test_coverage_absent"])
            uplift += add("multiplier.test_coverage_absent", subtotal, k - 1)
            notes.append(f"no automated test coverage declared: x{k}")
        code = [i for i in convert if ctx.objects[i].object_type in PROCEDURAL_TYPES | {"etl_job"}]
        dyn = [i for i in code if "dynamic_sql" in ctx.objects[i].constructs]
        share = len(dyn) / len(code) if code else 0.0
        limit = float(self.rubrics.get(mult["dynamic_sql_share"]["threshold_ref"]))
        if share > limit:
            k = float(mult["dynamic_sql_share"]["factor"])
            uplift += add("multiplier.dynamic_sql_share", subtotal, k - 1)
            notes.append(f"dynamic SQL in {share:.0%} of code objects (> {limit:.0%}): x{k}")
        converted = subtotal + uplift

        ai = mult["ai_acceleration"]
        add("ai_acceleration.conversion", converted, float(ai["conversion"]) - 1)
        shares = self.g("activity_shares")
        add("activity.testing", converted, float(shares["testing"]) * float(ai["test_generation"]))
        add("activity.documentation", converted, float(shares["documentation"]) * float(ai["documentation"]))
        notes.append(f"AI acceleration (hypothesis until measured): conversion x{ai['conversion']}, "
                     f"tests x{ai['test_generation']}, docs x{ai['documentation']}")

        if include_retired:
            retired = [i for i in ctx.retired()] if object_ids is None else [i for i in ids if i not in convert]
            if retired:
                add("retire_object", float(len(retired)), float(self.g("unit_effort_hours.retire_object")))
                notes.append(f"{len(retired)} objects to decommission")
        team = float(self.g("team_hours_per_week"))
        fixed = self.g("fixed_activities_weeks")
        if include_foundation:
            size = self._foundation_size(len(convert))
            add(f"fixed.foundation.{size}", float(fixed["foundation"][size]), team)
            notes.append(f"foundation ({size}): {fixed['foundation'][size]} weeks")
        if cutovers:
            cycles = float(fixed["parallel_run_cycles"]) * cutovers
            add("fixed.parallel_run", cycles, float(self.g("parallel_run_hours_per_cycle")))
            notes.append(f"{cycles:g} parallel-run cycles")

        p50 = _r2(sum(f["hours"] for f in factors.values()))
        comps = self.confidence_components(ids)
        weights = self.g("confidence.weights")
        confidence = round(sum(float(weights[k]) * v for k, v in comps.items()), 3)
        unc = self.g("uncertainty")
        spread = float(unc["p80_base_spread"]) + float(unc["p80_incompleteness_spread"]) * (1 - confidence)
        p80 = _r2(p50 * (1 + spread))
        notes.append(f"confidence {confidence:.2f} from data completeness "
                     + ", ".join(f"{k} {v:.2f}" for k, v in comps.items()) + f"; p80 = p50 x {1 + spread:.3f}")
        rows = [factors[k] for k in sorted(factors)]
        key = {"scope": scope, "ids": ids, "foundation": include_foundation, "retired": include_retired,
               "cutovers": cutovers, "inputs": {k: ctx.inputs.get(k) for k in sorted(ctx.inputs)}}
        eid = stable_id("EST", ctx.snapshot_id, self.rubrics.version, canonical_json(key), length=10)
        return Estimate(eid, scope, ctx.engagement_id, ctx.snapshot_id, ctx.assessment.harvest_snapshot_id,
                        self.rubrics.version, p50, p80, confidence, "; ".join(notes) + f"; rubric {self.rubrics.version}",
                        len(ids), rows, comps)

    def _foundation_size(self, n: int) -> str:
        sizes = self.g("foundation_size")
        if n >= int(sizes["large_min"]):
            return "large"
        if n >= int(sizes["medium_min"]):
            return "medium"
        return "small"

    def _mix(self, ids: list[str]) -> str:
        c = Counter(self.ctx.objects[i].object_type for i in ids)
        return ", ".join(f"{n} {t}" for t, n in sorted(c.items()))

    @staticmethod
    def _largest(factors: dict[str, dict[str, Any]]) -> str:
        if not factors:
            return "none"
        top = max(factors.values(), key=lambda f: (f["hours"], f["factor"]))
        return f"{top['factor']} {top['hours']:.2f}h"


def record_estimate(store: Any, est: Estimate, created_at: datetime | None = None) -> None:
    """Persist an estimate and its factors (idempotent by estimate id)."""
    if store.get("estimate", estimate_id=est.estimate_id):
        return
    store.insert("estimate", {
        "estimate_id": est.estimate_id, "engagement_id": est.engagement_id or "", "scope": est.scope,
        "snapshot_id": est.snapshot_id, "rubric_version": est.rubric_version, "p50_hours": est.p50_hours,
        "p80_hours": est.p80_hours, "confidence": est.confidence, "rationale": est.rationale,
        "created_at": created_at or datetime.now(timezone.utc).replace(tzinfo=None),
    })
    store.insert("estimate_factor", [{"estimate_id": est.estimate_id, **f} for f in est.factors])


def calibration_proposals(rubrics: RubricSet, actuals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare estimated vs actual hours per factor and propose new unit hours (never applied automatically).

    ``actuals``: ``[{"factor": "procedure_per_100_loc.high", "estimated_hours": 40, "actual_hours": 52}, ...]``.
    The result is reviewed by a practice lead and, if accepted, written into the rubric with a calibration entry.
    """
    unit = rubrics.get(R + "unit_effort_hours")
    by: dict[str, list[dict[str, Any]]] = {}
    for a in actuals:
        by.setdefault(a["factor"], []).append(a)
    out = []
    for factor, rows in sorted(by.items()):
        est = sum(float(r["estimated_hours"]) for r in rows)
        act = sum(float(r["actual_hours"]) for r in rows)
        node: Any = unit
        for part in factor.split("."):
            node = node.get(part) if isinstance(node, dict) else None
        if node is None or not est:
            continue
        ratio = act / est
        out.append({"factor": factor, "sample_size": len(rows), "estimated_hours": _r2(est), "actual_hours": _r2(act),
                    "ratio": round(ratio, 3), "current_unit_hours": float(node),
                    "proposed_unit_hours": round(float(node) * ratio, 3)})
    return out
