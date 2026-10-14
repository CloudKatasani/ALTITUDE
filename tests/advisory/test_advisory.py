import pytest

from altitude.advisory import ReviewBoard, Sherpa
from altitude.advisory.grounding import GroundingDoc, GroundingIndex, docs_from_suggestions
from altitude.core.errors import ApprovalRequired
from altitude.core.expr import ExpressionError, evaluate
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store

SUGGESTIONS = [
    {"id": "SUG-0001", "check_id": "DX-COST-01", "domain": "D1", "waf_pillar": "cost_optimization",
     "title": "Shorten auto-suspend on three idle-heavy warehouses",
     "affected_objects": ["WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"], "evidence_refs": ["EV-WH-0001", "EV-WH-0002"],
     "value": {"annualised_usd": {"p50": 84000, "conservative": 61000}, "method": "idle credits x price"},
     "confidence": 0.91, "rationale": "idle share above rubric threshold", "priority": {"quadrant": "quick_win"},
     "status": "proposed"},
    {"id": "SUG-0002", "check_id": "DX-SEC-01", "domain": "D4", "waf_pillar": "security_governance",
     "title": "Enforce MFA for humans and key-pair auth for service users",
     "affected_objects": ["JSMITH", "SVC_FIVETRAN"], "evidence_refs": ["EV-USR-0001"],
     "value": {"annualised_usd": {"p50": 0, "conservative": 0}, "method": "risk score"},
     "confidence": 0.95, "rationale": "humans without MFA", "priority": {"quadrant": "quick_win"}, "status": "proposed"},
]


def _index():
    idx = GroundingIndex()
    idx.add(docs_from_suggestions(SUGGESTIONS))
    idx.add([GroundingDoc("TD-01", "known_issue", "SET tables silently discard duplicate rows",
                          "Teradata SET table semantics; Snowflake keeps duplicates. Fix: QUALIFY ROW_NUMBER dedupe.",
                          ("teradata",))])
    return idx


def test_safe_expression_evaluator():
    rs = default_rubrics()
    assert evaluate("a < 26 and b > 0.4", {"a": 10, "b": 0.5}) is True
    assert evaluate("x is not None and x > rubric.advisory.challenges.deadline_weeks_tight", {"x": 30}, rs) is True
    with pytest.raises(ExpressionError):
        evaluate("__import__('os').system('true')", {})
    with pytest.raises(ExpressionError):
        evaluate("unknown > 1", {})


def test_sherpa_cites_evidence_and_refuses_when_ungrounded():
    store = Store()
    sherpa = Sherpa(_index(), store=store)
    ans = sherpa.ask("Which warehouses are idle and what does auto-suspend save?")
    assert ans.grounded and ans.citations[0] == "SUG-0001"
    assert "[SUG-0001]" in ans.text and 0 < ans.confidence <= 1
    refusal = sherpa.ask("What is the capital of Australia?")
    assert not refusal.grounded and refusal.citations == [] and refusal.confidence == 0.0
    # every answer is recorded with confidence + rationale; the refusal (low confidence) is queued for review
    assert store.scalar("SELECT count(*) FROM ai_inference") == 2
    assert store.query("SELECT subject_id FROM review_item")[0]["subject_id"].startswith("What is the capital")


def test_sherpa_exact_id_lookup_and_advisor_scope():
    sherpa = Sherpa(_index())
    assert sherpa.ask("explain TD-01").citations[0] == "TD-01"
    teradata = Sherpa.advisor("ADV-TERADATA", _index())
    ans = teradata.ask("duplicate rows after migrating SET tables")
    assert ans.citations == ["TD-01"]
    assert not teradata.ask("auto-suspend warehouses").grounded


def test_sherpa_challenges_risky_plan_unprompted():
    sherpa = Sherpa(_index())
    facts = {"pattern": "lift_and_shift", "procedural_object_count": 4200, "test_harness": False}
    ans = sherpa.ask("idle warehouses", facts)
    assert any(c["id"] == "SH-CH-001" and "4200" in c["message"] for c in ans.challenges)
    assert "SH-CH-001" in ans.text
    assert sherpa.challenges({"pattern": "re_platform", "procedural_object_count": 10, "test_harness": True}) == []


def test_next_three_actions():
    acts = Sherpa(_index()).next_actions("diagnose", {"access_confirmed": True, "snapshot_sealed": False,
                                                      "review_items_open": 4})
    assert len(acts) == 3 and "Clear the 4 low-confidence items" in acts[1]


def test_review_board_records_dissent_and_requires_human_decision():
    store = Store()
    board = ReviewBoard(store=store)
    res = board.review("Lift-and-shift wave 1", {"pattern": "lift_and_shift", "estimate_p80_weeks": 30,
                                                 "deadline_weeks": 26, "annual_value_usd": 900000,
                                                 "annual_cost_usd": 300000},
                       evidence_refs=["EST-1"], engagement_id="ENG-1")
    assert len(res.perspectives) == 7
    assert res.recommendation == "do_not_proceed_until_blockers_resolved"
    delivery = next(p for p in res.perspectives if p["lens"] == "DELIVERY")
    assert delivery["vote"] == "oppose"
    assert res.dissent and all(d["vote"] == "support" for d in res.dissent)
    row = store.get("decision", decision_id=res.decision_id)
    assert row["status"] == "proposed" and row["evidence_refs"] == ["EST-1"]
    with pytest.raises(ApprovalRequired):
        board.decide(res.decision_id, "", True)
    board.decide(res.decision_id, "cio@acme", False)
    assert store.get("decision", decision_id=res.decision_id)["status"] == "rejected"
    ok = board.review("Re-platform wave 2", {"pattern": "re_platform", "modernise_backlog": True,
                                             "annual_value_usd": 900000, "annual_cost_usd": 300000})
    assert ok.recommendation == "proceed"
    again = board.review("Re-platform wave 2", {"pattern": "re_platform", "modernise_backlog": True,
                                                "annual_value_usd": 900000, "annual_cost_usd": 300000})
    assert again.to_dict() == ok.to_dict()
