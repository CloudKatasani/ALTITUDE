"""Suggestion engine acceptance (MD): detection quality, complete suggestions, review flags, tiers."""

import json
from pathlib import Path

import jsonschema
import pytest

from altitude.core.ai import TemplateProvider
from altitude.core.generated import is_stamped
from altitude.core.rubric import default_rubrics
from altitude.diagnostics import DiagnosticsEngine
from altitude.synthetic.snowflake_account import score_detection

from diag_testdata import KPI_IDS

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "services/altitude/core/schemas/diagnostics_suggestion.json").read_text())


def test_seeded_account_detection_recall_and_false_positives(seeded_snapshot, seeded_result):
    _, account = seeded_snapshot
    score = score_detection(seeded_result.findings(), account)
    assert score["recall"] >= 0.9, score["missed"]
    assert score["false_positive_rate"] <= 0.1, score["false_positives"]
    # every one of the 33 seeded issue types is found
    assert {f["check_id"] for f in seeded_result.findings()} == {x["check_id"] for x in account.seeded}


def test_clean_account_is_near_silent(clean_snapshot, clean_result):
    _, account = clean_snapshot
    score = score_detection(clean_result.findings(), account)
    assert len(clean_result.findings()) <= 1
    assert score["false_positive_rate"] <= 0.1
    assert all(o.status != "not_evaluated" for o in clean_result.outcomes)


def test_every_suggestion_is_complete_and_canonical(seeded_result):
    assert seeded_result.suggestions
    canonical_keys = ["id", "snapshot_id", "check_id", "domain", "waf_pillar", "title", "evidence_refs", "affected_objects",
                      "value", "risk_reduction", "effort", "confidence", "rationale", "remediation", "kpis_to_watch",
                      "priority", "status", "reviewer"]
    evidence_ids = {e["id"] for e in seeded_result.evidence}
    for s in seeded_result.suggestions:
        jsonschema.validate(s, SCHEMA)
        assert list(s) == canonical_keys
        assert s["evidence_refs"] and set(s["evidence_refs"]) <= evidence_ids
        assert s["value"]["method"]
        assert s["value"]["annualised_usd"] or s["risk_reduction"], s["id"]
        if s["value"]["annualised_usd"]:
            assert s["value"]["annualised_usd"]["conservative"] <= s["value"]["annualised_usd"]["p50"]
        assert 0 < s["confidence"] <= 1 and s["rationale"]
        assert s["snapshot_id"] == seeded_result.snapshot_id and s["status"] == "proposed" and s["reviewer"] is None
        assert set(s["kpis_to_watch"]) <= KPI_IDS
        d = seeded_result.detail(s["id"])
        fwd, rb = s["remediation"]["artifact_ref"], s["remediation"]["rollback_ref"]
        assert set(d.artifacts) == {fwd, rb}
        for path in (fwd, rb):
            text = d.artifacts[path]
            assert is_stamped(text) and seeded_result.snapshot_id in text and seeded_result.rubric_version in text
        assert d.artifacts[rb].split("\n", 4)[-1].strip(), "rollback must contain statements"
        assert d.inference.confidence == s["confidence"] and d.inference.rationale and d.inference.provider == "template"
        assert d.narrative


def test_evidence_records_are_stable_and_traceable(seeded_result):
    for e in seeded_result.evidence:
        assert e["id"].startswith(f"EV-{e['kind']}-")
        assert e["snapshot_id"] == seeded_result.snapshot_id
        assert e["detector_ref"] == f"detectors/{e['check_id']}.sql" and e["detector_sha"]
        assert e["metrics"] and e["source_tables"]


def test_clustering_groups_by_root_cause(seeded_result):
    by_check = {}
    for d in seeded_result.details:
        by_check.setdefault(d.record["check_id"], []).append(d)
    cost01 = by_check["DX-COST-01"]
    assert len(cost01) == 1 and cost01[0].record["affected_objects"] == ["WH_BI_ADHOC", "WH_BI_PROD", "WH_DEV"]
    assert {d.cluster_key for d in by_check["DX-SEC-03"]} == {"dormant_user", "orphan_role"}
    assert by_check["DX-BI-01"][0].cluster_dimension == "dashboard"
    assert by_check["DX-PERF-02"][0].cluster_dimension == "query_signature"
    assert by_check["DX-REL-01"][0].cluster_dimension == "pipeline"


def test_value_model_uses_contract_price(seeded_result):
    ctx = seeded_result.context
    assert ctx.price_source == "client_input" and ctx.price_per_credit == 3.0
    d = next(x for x in seeded_result.details if x.record["check_id"] == "DX-COST-01")
    ev = seeded_result.evidence_for(d.record)
    rubrics = default_rubrics()
    idle = sum(e["metrics"]["IDLE_CREDITS"] for e in ev)
    expected = idle * rubrics.get("rubric.diagnostics.checks.cost_01.recoverable_idle_share") * 3.0 * ctx.annualise
    assert d.record["value"]["annualised_usd"]["p50"] == pytest.approx(expected, abs=2)


def test_low_confidence_suggestions_require_review(seeded_result):
    floor = default_rubrics().get("rubric.ai.review_confidence_min")
    low = [d for d in seeded_result.details if d.record["confidence"] < floor]
    assert low, "heuristic (low-class) detectors land below the review floor"
    assert all(d.needs_review and d.review_reason == "low_confidence" for d in low)
    assert all(not d.needs_review for d in seeded_result.details if d.record["confidence"] >= floor)


def test_prioritisation_quadrants_and_ranks(seeded_result):
    ranks = [s["priority"]["rank"] for s in seeded_result.suggestions]
    assert ranks == list(range(1, len(ranks) + 1))
    assert {s["priority"]["quadrant"] for s in seeded_result.suggestions} <= {"quick_win", "strategic", "hygiene", "defer"}
    rubrics = default_rubrics()
    for s in seeded_result.suggestions:
        low_effort = s["effort"]["hours_p50"] <= rubrics.get("rubric.diagnostics.priority.low_effort_hours_max")
        assert (s["priority"]["quadrant"] in {"quick_win", "hygiene"}) == low_effort


def test_d0_tier_scope_and_top_findings(seeded_snapshot):
    snap, _ = seeded_snapshot
    res = DiagnosticsEngine().run(snap, tier="D0")
    assert len(res.suggestions) == 10
    assert {s["domain"] for s in res.suggestions} <= {"D1", "D2", "D3", "D4", "D5"}
    assert {o.check_id.split("-")[1] for o in res.outcomes} <= {"COST", "PERF", "REL", "SEC", "GOV"}
    in_scope = [d["id"] for d in res.scorecard["domains"] if d["in_scope"]]
    assert in_scope == ["D1", "D2", "D3", "D4", "D5"]


def test_narrative_uses_the_configured_provider(seeded_snapshot):
    snap, _ = seeded_snapshot

    class FakeLLM(TemplateProvider):
        name = "cortex"
        model_id = "fake-model"

        def complete(self, system, data):
            assert "<untrusted_facts" in data  # facts are fenced as data, never instructions
            return "LLM narrative."

    res = DiagnosticsEngine(provider=FakeLLM()).run(snap, tier="D0")
    d = res.details[0]
    assert d.narrative == "LLM narrative." and d.inference.provider == "cortex" and d.inference.model_id == "fake-model"
    assert d.inference.confidence == d.record["confidence"]


def test_rubric_change_changes_rubric_version_and_values(seeded_snapshot, seeded_result):
    snap, _ = seeded_snapshot
    rubrics = default_rubrics().with_overrides({"diagnostics": {"checks": {"cost_01": {"recoverable_idle_share": 0.35}}}})
    res = DiagnosticsEngine(rubrics=rubrics).run(snap, tier="D2")
    assert res.rubric_version != seeded_result.rubric_version
    p50 = lambda r: next(s for s in r.suggestions if s["check_id"] == "DX-COST-01")["value"]["annualised_usd"]["p50"]  # noqa: E731
    assert p50(res) == pytest.approx(p50(seeded_result) / 2, abs=2)
