"""Acceptance (M4, part 1): estimates reference the rubric version and are reproducible; gates are data."""

import pytest
import yaml

from altitude.assessment import record
from altitude.core.paths import knowledge_dir
from altitude.core.ai import ReviewQueue
from altitude.core.errors import AppendOnlyViolation
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude.planning import Estimator, calibration_proposals, collect_metrics, evaluate_gate, gate_passed, record_gate
from altitude.planning.estimation import record_estimate


def test_estimate_references_rubric_version_and_is_reproducible(ctx_for):
    rs = default_rubrics()
    a = Estimator(ctx_for(), rs).estimate("programme", None, include_foundation=True, include_retired=True, cutovers=2)
    b = Estimator(ctx_for(), rs).estimate("programme", None, include_foundation=True, include_retired=True, cutovers=2)
    assert a.to_dict() == b.to_dict()  # same snapshot + rubric version ⇒ identical estimate
    assert a.rubric_version == rs.version and a.rubric_version in a.rationale
    assert a.snapshot_id == ctx_for().snapshot_id and a.harvest_snapshot_id == ctx_for().assessment.harvest_snapshot_id
    assert a.p80_hours > a.p50_hours > 0 and 0 < a.confidence <= 1
    assert sum(f["hours"] for f in a.factors) == pytest.approx(a.p50_hours, abs=0.05)
    names = {f["factor"] for f in a.factors}
    assert {"table_ddl", "view_simple", "fixed.parallel_run", "ai_acceleration.conversion", "activity.testing",
            "retire_object", "multiplier.test_coverage_absent"} <= names
    assert any(n.startswith("procedure_per_100_loc.") for n in names) and any(n.startswith("etl_job.") for n in names)
    assert any(n.startswith("fixed.foundation.") for n in names)
    assert next(f for f in a.factors if f["factor"] == "fixed.parallel_run")["quantity"] == 4  # 2 cycles x 2 cutovers


def test_estimate_changes_with_rubric_and_records_version(ctx_for):
    rs = default_rubrics()
    base = Estimator(ctx_for(), rs).estimate("programme")
    rs2 = rs.with_overrides({"estimation": {"unit_effort_hours": {"table_ddl": 1.0}}})
    other = Estimator(ctx_for(), rs2).estimate("programme")
    assert other.rubric_version != base.rubric_version and other.estimate_id != base.estimate_id
    assert other.p50_hours > base.p50_hours
    store = Store()
    record_estimate(store, base)
    record_estimate(store, base)  # idempotent
    row = store.get("estimate", estimate_id=base.estimate_id)
    assert row["rubric_version"] == rs.version and row["snapshot_id"] == base.snapshot_id
    assert float(row["p50_hours"]) == pytest.approx(base.p50_hours)
    assert store.scalar("SELECT count(*) FROM estimate_factor WHERE estimate_id = ?", [base.estimate_id]) == \
        len(base.factors)


def test_confidence_reflects_data_completeness(ctx_for):
    full = Estimator(ctx_for()).estimate("programme")
    sparse = Estimator(ctx_for(deadline_weeks=None, appetite_for_change=None, model_quality_score=None,
                                budget_band=None, test_coverage=None)).estimate("programme")
    assert sparse.confidence_components["programme_inputs"] == 0
    assert sparse.confidence < full.confidence
    assert (sparse.p80_hours / sparse.p50_hours) > (full.p80_hours / full.p50_hours)  # wider band


def test_calibration_proposals_are_proposals():
    rs = default_rubrics()
    props = calibration_proposals(rs, [
        {"factor": "procedure_per_100_loc.high", "estimated_hours": 40, "actual_hours": 50},
        {"factor": "procedure_per_100_loc.high", "estimated_hours": 20, "actual_hours": 25},
        {"factor": "not_a_factor", "estimated_hours": 1, "actual_hours": 2},
    ])
    assert props == [{"factor": "procedure_per_100_loc.high", "sample_size": 2, "estimated_hours": 60.0,
                      "actual_hours": 75.0, "ratio": 1.25, "current_unit_hours": 10.0, "proposed_unit_hours": 12.5}]
    assert rs.get("rubric.estimation.unit_effort_hours.procedure_per_100_loc.high") == 10  # never auto-applied
    # calibration history (dates, sample sizes) lives with the rubric file and is schema-validated
    doc = yaml.safe_load((knowledge_dir() / "rubrics" / "estimation.yaml").read_text())
    assert doc["calibration"] and all({"date", "sample_size", "note"} <= set(c) for c in doc["calibration"])


def test_assess_exit_gate_evaluated_from_evidence_and_recorded(estates):
    harvest, assessment = estates["sqlserver"]
    store = Store()
    record(assessment, store)
    eng = assessment.summary["engagement_id"]
    m = collect_metrics(assessment=assessment, store=store)
    assert m["objects_classified_pct"] < 95  # low-confidence items still in review
    d1 = record_gate(store, evaluate_gate("assess_exit", m, snapshot_id=assessment.snapshot_id, engagement_id=eng))
    assert d1.result == "fail"
    statuses = {c["metric"]: c["status"] for c in d1.criteria}
    assert statuses == {"objects_classified_pct": "fail", "tier1_identified": "missing",
                        "business_case_approved": "missing"}
    assert not gate_passed(store, "assess_exit", assessment.snapshot_id)

    q = ReviewQueue(store)
    for item in q.open_items("object_disposition"):
        q.decide(item["item_id"], "lead.architect", "approved")
    store.insert("approval", {"approval_id": "APR-BC-1", "subject_type": "business_case", "subject_id": eng,
                              "approver": "cfo@client", "decision": "approved", "decided_at": "2026-10-10"})
    m2 = collect_metrics(assessment=assessment, store=store, facts={"tier1_identified": True})
    assert m2["objects_classified_pct"] == 100 and m2["business_case_approved"] is True
    d2 = record_gate(store, evaluate_gate("assess_exit", m2, snapshot_id=assessment.snapshot_id, engagement_id=eng))
    assert d2.passed and d2.gate_id != d1.gate_id
    rows = store.all("gate", order_by="decided_at")
    assert [r["result"] for r in rows] == ["fail", "pass"]  # append-only history of decisions
    assert all(r["snapshot_id"] == assessment.snapshot_id and r["rubric_version"] for r in rows)
    assert gate_passed(store, "assess_exit", assessment.snapshot_id)
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE gate SET result = 'pass'")
    with pytest.raises(AppendOnlyViolation):
        store.execute("DELETE FROM gate")


def test_gate_thresholds_are_rubric_data(estates):
    _, assessment = estates["sqlserver"]
    metrics = {"objects_classified_pct": 90.0, "tier1_identified": True, "business_case_approved": True}
    strict = evaluate_gate("assess_exit", metrics, snapshot_id=assessment.snapshot_id, engagement_id="E")
    lenient_rs = default_rubrics().with_overrides({"gates": {"assess_classified_min": 85}})
    lenient = evaluate_gate("assess_exit", metrics, snapshot_id=assessment.snapshot_id, engagement_id="E",
                            rubrics=lenient_rs)
    assert strict.result == "fail" and lenient.result == "pass"
    assert lenient.criteria[0]["expected"] == 85 and lenient.criteria[0]["expected_from"] == "rubric.gates.assess_classified_min"
    cut = evaluate_gate("cutover_go", {"tier1_l3_mismatches_unaccepted": 0, "consecutive_clean_parallel_cycles": 2,
                                       "rollback_rehearsed": True, "grants_mapped_pct": 100},
                        snapshot_id="S", engagement_id="E")
    assert cut.passed
    with pytest.raises(Exception):
        evaluate_gate("no_such_gate", {}, snapshot_id="S", engagement_id="E")
