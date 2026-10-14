from datetime import date, datetime

import pytest

from altitude.core.errors import ApprovalRequired
from altitude.core.store import Store
from altitude.cutover import build_go_no_go_pack, decide, decommission_readiness, render_markdown, savings_realisation

NOW = datetime(2026, 10, 1)


def _seed(store, l3_fail=True, accept=False, rehearsed=True, unmapped=0):
    store.insert("source_system", {"source_system_id": "SRC1", "engagement_id": "ENG1", "dialect": "sqlserver",
                                   "name": "EDW"})
    store.insert("validation_suite", {"suite_id": "S1", "engagement_id": "ENG1", "object_id": "O1", "tier": "tier1",
                                      "levels": ["L0", "L1", "L3"], "generated_at": NOW})
    for i, (lvl, res) in enumerate([("L0", "pass"), ("L1", "pass"), ("L3", "fail" if l3_fail else "pass")]):
        store.insert("validation_run", {"run_id": f"R{i}", "suite_id": "S1", "object_id": "O1", "level": lvl,
                                        "normalisation_rule_version": "n1", "threshold_rubric_version": "r1",
                                        "result": res, "metrics": {"rows": 10}, "executed_in": "client_agent",
                                        "completed_at": NOW})
    if accept:
        store.insert("accepted_deviation", {"deviation_id": "D1", "run_id": "R2", "description": "trailing spaces",
                                            "approver": "owner@acme", "approved_at": NOW, "review_by": date(2027, 1, 1)})
    for i in range(4):
        store.insert("grant", {"grant_id": f"G{i}", "source_system_id": "SRC1", "grantee": f"u{i}", "grantee_type": "user",
                               "privilege": "SELECT", "mapping_status": "mapped" if i >= unmapped else None})
    store.insert("cutover_plan", {"plan_id": "P1", "engagement_id": "ENG1", "strategy": "parallel_run",
                                  "scope": "Finance wave 1"})
    store.insert("rollback_plan", {"rollback_id": "RB1", "plan_id": "P1", "steps": {"1": "repoint"}, "rehearsed": rehearsed})
    if rehearsed:
        store.insert("rehearsal", {"rehearsal_id": "RH1", "plan_id": "P1", "executed_at": NOW, "result": "success"})


FACTS = {"parallel_cycles": [{"date": "2026-09-29", "clean": True, "month_end": False},
                             {"date": "2026-09-30", "clean": True, "month_end": True}],
         "uat_signoffs": {"finance": "cfo@acme", "ops": "ops@acme"}, "open_defects": {"S1": 0, "S2": 3},
         "runbook_ready": True, "on_call_ready": True, "agent_fleet_healthy": True}


def test_unaccepted_tier1_mismatch_blocks_go():
    s = Store()
    _seed(s, l3_fail=True)
    pack = build_go_no_go_pack(s, "ENG1", "P1", "SNAP-1", FACTS)
    assert pack["recommendation"] == "no_go"
    failed = {c["metric"] for c in pack["criteria"] if not c["passed"]}
    assert failed == {"tier1_l3_mismatches_unaccepted"}
    with pytest.raises(ApprovalRequired):
        decide(s, pack["go_no_go_id"], "cio@acme", "go")
    decide(s, pack["go_no_go_id"], "cio@acme", "go", override_reason="deviation accepted verbally; paper follows")
    assert s.get("go_no_go", go_no_go_id=pack["go_no_go_id"])["decided_by"] == "cio@acme"


def test_accepted_deviation_and_full_evidence_gives_go_and_reproducible_pack():
    s = Store()
    _seed(s, l3_fail=True, accept=True)
    pack = build_go_no_go_pack(s, "ENG1", "P1", "SNAP-1", FACTS)
    assert pack["recommendation"] == "go"
    assert pack["sections"]["reconciliation"]["by_tier"]["tier1"]["accepted_deviation"] == 1
    again = build_go_no_go_pack(s, "ENG1", "P1", "SNAP-1", FACTS)
    assert again["pack_hash"] == pack["pack_hash"]
    md = render_markdown(pack)
    assert "Recommendation: **GO**" in md and "{{" not in md


def test_missing_month_end_rollback_and_grants():
    s = Store()
    _seed(s, l3_fail=False, rehearsed=False, unmapped=1)
    facts = dict(FACTS, parallel_cycles=[{"clean": True, "month_end": False}] * 3,
                 uat_signoffs={"finance": None})
    pack = build_go_no_go_pack(s, "ENG1", "P1", "SNAP-2", facts)
    failed = {c["metric"] for c in pack["criteria"] if not c["passed"]}
    assert failed == {"consecutive_clean_parallel_cycles", "rollback_rehearsed", "grants_mapped_pct",
                      "uat_signoffs_missing"}


def test_decommission_blocked_by_active_consumers():
    s = Store()
    s.insert("source_object", {"object_id": "O1", "engagement_id": "E", "source_system_id": "SRC1", "object_type": "table",
                               "fq_name": "dbo.Orders", "harvested_at": NOW})
    s.insert("usage_stat", {"object_id": "O1", "period_start": date(2026, 9, 20), "period_end": date(2026, 9, 26),
                            "query_count": 5, "distinct_users": 1})
    r = decommission_readiness(s, "SRC1", date(2026, 10, 1))
    assert r["blocked"] and r["active_consumers"][0]["fq_name"] == "dbo.Orders"
    assert not decommission_readiness(s, "SRC1", date(2026, 12, 31))["blocked"]
    rep = savings_realisation({"licence": 900000, "hardware": 250000}, 400000, decommissioned=True)
    assert rep["realised_annual_savings"] == 750000
    assert savings_realisation({"licence": 1}, 0, decommissioned=False)["realised_annual_savings"] == 0
