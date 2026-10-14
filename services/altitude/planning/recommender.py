"""Pattern recommender (Section 8.3) — rules as data in ``rubric.pattern_recommender``.

Rules are evaluated in order with the safe evaluator; the first matching rule
wins, otherwise the default applies. A rule that references an input with no
value is *not evaluable* (recorded, never guessed). Output: pattern, confidence
(rule confidence scaled by input completeness), rationale and dissent from the
review-board lenses (and from later rules that also matched).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from altitude.core.ids import canonical_json, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .context import PROCEDURAL_TYPES, PlanningContext
from .safe_eval import MissingInput, evaluate_bool

R = "rubric.pattern_recommender."


@dataclass
class Recommendation:
    recommendation_id: str
    scope: str
    pattern: str
    confidence: float
    rationale: str
    rule_id: str
    dissent: list[dict[str, Any]] = field(default_factory=list)
    inputs: dict[str, Any] = field(default_factory=dict)
    missing_inputs: list[str] = field(default_factory=list)
    unevaluated: list[dict[str, str]] = field(default_factory=list)
    rubric_version: str = ""
    snapshot_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evidence_inputs(ctx: PlanningContext, object_ids: Iterable[str], tags: dict[str, set[str]] | None = None
                    ) -> dict[str, Any]:
    """Recommender inputs computed from evidence for a set of objects (a wave or the programme)."""
    ids = list(object_ids)
    objs = [ctx.objects[i] for i in ids]
    code = [o for o in objs if o.object_type != "table"]
    code_loc = sum(o.loc for o in code)
    proc_loc = sum(o.loc for o in code if o.object_type in PROCEDURAL_TYPES)
    etl = [o for o in objs if o.object_type == "etl_job"]
    etl_complex = [o for o in etl if o.band != "low" or "script_task" in o.constructs]
    total = len(ctx.objects)
    tags = tags if tags is not None else ctx.tags()
    return {
        "procedural_code_share": round(proc_loc / code_loc, 3) if code_loc else 0.0,
        "dead_object_share": round(len(ctx.retired()) / total, 3) if total else 0.0,
        "etl_tool_complexity": round(len(etl_complex) / len(etl), 3) if etl else 0.0,
        "regulatory_freeze_windows": sum(1 for i in ids if tags.get(i, set()) & {"regulatory", "month_end"}),
    }


def recommend(inputs: dict[str, Any], *, scope: str, snapshot_id: str, rubrics: RubricSet | None = None
              ) -> Recommendation:
    rubrics = rubrics or default_rubrics()
    names = list(rubrics.get(R + "inputs"))
    env = {k: inputs.get(k) for k in names}
    missing = [k for k in names if env[k] is None]
    completeness = (len(names) - len(missing)) / len(names) if names else 1.0
    floor = float(rubrics.get(R + "completeness_floor"))
    scale = floor + (1 - floor) * completeness

    matched: list[dict[str, Any]] = []
    unevaluated: list[dict[str, str]] = []
    for rule in rubrics.get(R + "rules"):
        try:
            if evaluate_bool(rule["when"], env, rubrics):
                matched.append(rule)
        except MissingInput as e:
            unevaluated.append({"rule": rule["id"], "missing": e.name})
    default = rubrics.get(R + "default")
    chosen = matched[0] if matched else {"id": "default", **default}
    pattern = chosen["recommend"]
    confidence = round(float(chosen["confidence"]) * scale, 3)
    why = [chosen["rationale"]]
    if matched:
        why.append(f"rule '{chosen['id']}' matched: {chosen['when']}")
    else:
        why.append("no rule matched" + (f" ({len(unevaluated)} not evaluable for missing inputs)" if unevaluated else ""))
    why.append("inputs: " + ", ".join(f"{k}={env[k]}" for k in names if env[k] is not None))
    if missing:
        why.append(f"missing inputs ({', '.join(missing)}) reduce confidence x{scale:.2f}")

    dissent = [{"lens": f"rule:{r['id']}", "prefers": r["recommend"], "rationale": r["rationale"]}
               for r in matched[1:] if r["recommend"] != pattern]
    for lens in rubrics.get(R + "review_board"):
        try:
            if evaluate_bool(lens["when"], env, rubrics) and lens["prefers"] != pattern:
                dissent.append({"lens": lens["lens"], "prefers": lens["prefers"], "rationale": lens["rationale"]})
        except MissingInput:
            continue
    rid = stable_id("REC", scope, snapshot_id, rubrics.version, canonical_json(env), length=10)
    return Recommendation(rid, scope, pattern, confidence, "; ".join(why), chosen["id"], dissent, env, missing,
                          unevaluated, rubrics.version, snapshot_id)


def record_recommendation(store: Any, rec: Recommendation, engagement_id: str | None) -> None:
    if store.get("pattern_recommendation", recommendation_id=rec.recommendation_id):
        return
    store.insert("pattern_recommendation", {
        "recommendation_id": rec.recommendation_id, "engagement_id": engagement_id or "", "scope": rec.scope,
        "pattern": rec.pattern, "confidence": rec.confidence, "rationale": rec.rationale,
        "dissent": canonical_json(rec.dissent),
        "rubric_version": rec.rubric_version, "snapshot_id": rec.snapshot_id,
    })
