"""Same snapshot + rubric version ⇒ identical scores, values and exported bytes; scorecard semantics."""

import pytest

from altitude.core.rubric import default_rubrics
from altitude.core.snapshot import Snapshot
from altitude.diagnostics import DiagnosticsEngine
from altitude.diagnostics.exports import ado_csv, evidence_json, findings_csv, jira_csv, pr_pack, suggestions_json
from altitude.diagnostics.report import render_report
from altitude.diagnostics.scorecard import compute_scorecard


def _texts(r):
    return {
        "suggestions.json": suggestions_json(r), "evidence.json": evidence_json(r), "findings.csv": findings_csv(r),
        "jira.csv": jira_csv(r), "ado.csv": ado_csv(r), "report.html": render_report(r), **pr_pack(r),
    }


def test_same_snapshot_and_rubric_reproduce_identical_outputs(seeded_snapshot, seeded_result):
    snap, _ = seeded_snapshot
    again = DiagnosticsEngine().run(Snapshot.open(snap.path, verify=True), tier="D2")
    assert again.rubric_version == seeded_result.rubric_version
    assert again.scorecard == seeded_result.scorecard
    assert again.suggestions == seeded_result.suggestions
    assert again.evidence == seeded_result.evidence
    a, b = _texts(seeded_result), _texts(again)
    assert a.keys() == b.keys()
    for name in a:
        assert a[name].encode() == b[name].encode(), f"{name} differs between runs"


def test_exports_carry_snapshot_and_rubric_version(seeded_result):
    for name, text in _texts(seeded_result).items():
        assert seeded_result.snapshot_id in text, name
        assert seeded_result.rubric_version in text, name


def test_scorecard_ranges_and_roll_up(seeded_result, clean_result):
    for res in (seeded_result, clean_result):
        sc = res.scorecard
        assert [d["id"] for d in sc["domains"]] == [f"D{i}" for i in range(1, 11)]
        assert all(1 <= d["score"] <= 5 for d in sc["domains"])
        assert len(sc["pillars"]) == 5 and all(1 <= p["score"] <= 5 for p in sc["pillars"])
        assert 0 <= sc["platform_health_index"] <= 100
    assert clean_result.scorecard["platform_health_index"] == 100.0
    assert seeded_result.scorecard["platform_health_index"] < 50
    assert all(d["score"] == 5 for d in clean_result.scorecard["domains"])


def test_scorecard_is_a_pure_function_of_outcomes_and_rubric(seeded_result):
    from altitude.diagnostics import default_catalogue

    cat = default_catalogue()
    rubrics = default_rubrics()
    assert compute_scorecard(seeded_result.outcomes, cat, rubrics, "D2") == seeded_result.scorecard
    stricter = rubrics.with_overrides({"diagnostics": {"scorecard": {"failing_check_credit_max": 0.0}}})
    sc = compute_scorecard(seeded_result.outcomes, cat, stricter, "D2")
    assert sc["platform_health_index"] < seeded_result.scorecard["platform_health_index"]
    weights = rubrics.get("rubric.diagnostics.scorecard.domain_weights")
    assert sum(weights.values()) == pytest.approx(1.0)


def test_recommender_suggests_next_packages(seeded_result, clean_result):
    ids = {r["id"] for r in seeded_result.recommendations}
    assert {"NXT-FINOPS", "NXT-SECURITY", "NXT-BI", "NXT-AIREADY", "NXT-MANAGED-RUN"} <= ids
    assert "NXT-MIGRATION" not in ids  # no legacy sources in the intake
    assert clean_result.recommendations == []
