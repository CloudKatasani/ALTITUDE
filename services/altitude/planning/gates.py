"""Readiness gates (Appendix C) as data in ``rubric.gates.definitions``.

A gate is a list of criteria ``{metric, op, value | ref}``. Metrics come from
evidence (assessment snapshot, store records) or explicitly supplied facts
(e.g. ``business_case_approved``); a metric with no evidence fails its
criterion — gates are evidence-based. Every evaluation is recorded in the
append-only ``gate`` table against the snapshot it was evaluated on.
"""

from __future__ import annotations

import operator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from altitude.core.ai import ReviewQueue
from altitude.core.errors import AltitudeError
from altitude.core.ids import canonical_json, stable_id
from altitude.core.rubric import RubricSet, default_rubrics, is_ref

OPS: dict[str, Callable[[Any, Any], bool]] = {
    "==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt,
}
EVALUATOR = "altitude.planning.gates"


@dataclass
class GateDecision:
    gate_id: str
    gate_key: str
    engagement_id: str
    snapshot_id: str
    rubric_version: str
    result: str  # pass | fail
    criteria: list[dict[str, Any]] = field(default_factory=list)
    decided_by: str = EVALUATOR

    @property
    def passed(self) -> bool:
        return self.result == "pass"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def gate_definition(gate_key: str, rubrics: RubricSet | None = None) -> list[dict[str, Any]]:
    rubrics = rubrics or default_rubrics()
    defs = rubrics.get("rubric.gates.definitions")
    if gate_key not in defs:
        raise AltitudeError(f"unknown gate {gate_key!r}; defined: {', '.join(sorted(defs))}")
    return list(defs[gate_key])


def evaluate_gate(gate_key: str, metrics: dict[str, Any], *, snapshot_id: str, engagement_id: str,
                  rubrics: RubricSet | None = None, decided_by: str = EVALUATOR) -> GateDecision:
    """Pure evaluation of one gate against metric values."""
    rubrics = rubrics or default_rubrics()
    criteria = []
    for c in gate_definition(gate_key, rubrics):
        expected = rubrics.get(c["ref"]) if is_ref(c.get("ref")) else c.get("value")
        actual = metrics.get(c["metric"])
        if actual is None:
            status, ok = "missing", False
        else:
            try:
                ok = bool(OPS[c["op"]](actual, expected))
            except TypeError:
                ok = False
            status = "pass" if ok else "fail"
        criteria.append({"metric": c["metric"], "op": c["op"], "expected": expected,
                         "expected_from": c.get("ref") or "literal", "actual": actual, "status": status})
    result = "pass" if all(c["status"] == "pass" for c in criteria) else "fail"
    gid = stable_id("GATE", engagement_id, gate_key, snapshot_id, rubrics.version, canonical_json(criteria), length=10)
    return GateDecision(gid, gate_key, engagement_id, snapshot_id, rubrics.version, result, criteria, decided_by)


def record_gate(store: Any, decision: GateDecision, decided_at: datetime | None = None) -> GateDecision:
    """Append the decision to the ``gate`` table (idempotent; existing decisions are never modified)."""
    if not store.get("gate", gate_id=decision.gate_id):
        store.insert("gate", {
            "gate_id": decision.gate_id, "engagement_id": decision.engagement_id, "gate_key": decision.gate_key,
            "snapshot_id": decision.snapshot_id, "rubric_version": decision.rubric_version, "result": decision.result,
            "details": {"criteria": decision.criteria}, "decided_by": decision.decided_by,
            "decided_at": decided_at or datetime.now(timezone.utc).replace(tzinfo=None),
        })
    return decision


def latest_decision(store: Any, gate_key: str, snapshot_id: str) -> dict[str, Any] | None:
    rows = store.query("SELECT * FROM gate WHERE gate_key = ? AND snapshot_id = ? ORDER BY decided_at DESC, gate_id",
                       [gate_key, snapshot_id])
    return rows[0] if rows else None


def gate_passed(store: Any, gate_key: str, snapshot_id: str | None = None, engagement_id: str | None = None) -> bool:
    if snapshot_id is not None:
        row = latest_decision(store, gate_key, snapshot_id)
    else:
        rows = store.query("SELECT * FROM gate WHERE gate_key = ? AND engagement_id = ? ORDER BY decided_at DESC, "
                           "gate_id", [gate_key, engagement_id])
        row = rows[0] if rows else None
    return bool(row) and row["result"] == "pass"


# --------------------------------------------------------------------------- evidence metrics


def collect_metrics(*, assessment: Any = None, plan: Any = None, store: Any = None,
                    facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Metric values from evidence; explicit ``facts`` (human-attested, e.g. sign-offs) fill the rest."""
    m: dict[str, Any] = {}
    if assessment is not None:
        rows = assessment.rows("object_disposition")
        cleared = set()
        if store is not None:
            q = ReviewQueue(store)
            cleared = {r["object_id"] for r in rows if r["needs_review"]
                       and store.query("SELECT 1 FROM review_item WHERE subject_type = 'object_disposition' AND "
                                       "subject_id = ?", [r["object_id"]])
                       and q.is_cleared("object_disposition", r["object_id"])}
        classified = [r for r in rows if not r["needs_review"] or r["object_id"] in cleared]
        m["objects_classified_pct"] = round(100.0 * len(classified) / len(rows), 2) if rows else 0.0
    if plan is not None:
        m["wave_rule_violations"] = len(plan.violations)
    if store is not None:
        ids = None
        if assessment is not None:
            ids = [r["object_id"] for r in assessment.rows("object_disposition")]
        if ids:
            marks = ", ".join("?" for _ in ids)
            n = store.scalar(f"SELECT count(*) FROM tier WHERE tier = 'tier1' AND object_id IN ({marks})", ids)
            if n:
                m["tier1_identified"] = True
        for key, subject in (("business_case_approved", "business_case"),
                             ("architecture_board_approved", "architecture"), ("wave1_scope_frozen", "wave1_scope")):
            row = store.query("SELECT decision FROM approval WHERE subject_type = ? ORDER BY decided_at DESC",
                              [subject])
            if row:
                m[key] = row[0]["decision"] == "approved"
        m["open_p1_ewis"] = store.scalar("SELECT count(*) FROM conversion_issue WHERE severity IN ('P1', 'S1') "
                                         "AND status = 'open'")
        m["ai_changes_unreviewed"] = store.scalar("SELECT count(*) FROM ai_change WHERE decision IS NULL")
        grants = store.scalar('SELECT count(*) FROM "grant"')
        if grants:
            mapped = store.scalar("SELECT count(*) FROM \"grant\" WHERE mapping_status IN ('mapped', 'retired')")
            m["grants_mapped_pct"] = round(100.0 * mapped / grants, 2)
    m.update({k: v for k, v in (facts or {}).items() if v is not None})
    return m
