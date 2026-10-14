"""Suggestion-to-value loop (Section 7.12): implemented suggestions are measured before vs after in-account."""

import json
from datetime import date

import pytest

from altitude.core.errors import AppendOnlyViolation
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude.observability.db import ObsDatabase
from altitude.observability.harvest import harvest_account
from altitude.observability.kpi import compute_kpis
from altitude.observability.sources import SyntheticSource
from altitude.observability.value import current_status, measure_suggestions, qbr_summary, windows
from altitude.synthetic import AccountSpec

IMPLEMENTED = date(2026, 9, 15)

SUGGESTIONS = [
    {"id": "SUG-0142", "snapshot_id": "SNAP-ACME-2026-09-01", "check_id": "DX-COST-01",
     "title": "Shorten auto-suspend on three BI/dev warehouses",
     "affected_objects": ["WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"],
     "value": {"annualised_usd": {"p50": 84000, "conservative": 61000}, "method": "idle credits x price"},
     "kpis_to_watch": ["KPI-COST-007", "KPI-PERF-002"], "status": "implemented",
     "implemented_at": IMPLEMENTED.isoformat()},
    {"id": "SUG-0150", "check_id": "DX-PERF-01", "affected_objects": ["WH_BI_PROD"],
     "value": {"annualised_usd": {"p50": 12000}}, "kpis_to_watch": ["KPI-PERF-002"], "status": "implemented",
     "implemented_at": IMPLEMENTED.isoformat()},
    {"id": "SUG-0151", "check_id": "DX-SEC-01", "value": {"annualised_usd": {"p50": 0}},
     "kpis_to_watch": ["KPI-SEC-001"], "status": "implemented", "implemented_at": "2026-09-25"},
    {"id": "SUG-0160", "check_id": "DX-COST-06", "value": {"annualised_usd": {"p50": 9000}},
     "kpis_to_watch": ["KPI-COST-009"], "status": "proposed"},
]


@pytest.fixture(scope="module")
def obs_fixed():
    """The client implements DX-COST-01 on 2026-09-15: the account is harvested before and after the change."""
    db = ObsDatabase()
    harvest_account(db, SyntheticSource(AccountSpec(end_date=date(2026, 9, 14), days=30), native_retention_days=30),
                    date(2026, 9, 14))
    after = AccountSpec(end_date=date(2026, 9, 30), days=16, disabled_issues={"DX-COST-01"})
    harvest_account(db, SyntheticSource(after, native_retention_days=16), date(2026, 9, 30))
    compute_kpis(db)
    return db


@pytest.fixture(scope="module")
def measured(obs_fixed):
    store = Store()
    out = measure_suggestions(obs_fixed, SUGGESTIONS, store=store, tenant_id="TEN-EXAMPLE")
    return store, {s["id"]: s for s in out}


def test_implemented_suggestion_improvement_is_measured_and_recorded(measured):
    store, out = measured
    s = out["SUG-0142"]
    assert s["status"] == "value_realised"
    realised = s["value"]["realised"]
    assert realised["outcome"] == "value_realised" and realised["annualised_usd"] > 0
    idle = next(k for k in realised["measured_kpis"] if k["kpi_id"] == "KPI-COST-007")
    assert idle["improved"] and idle["after"] < idle["before"] and idle["delta_pct"] < 0
    queued = next(k for k in realised["measured_kpis"] if k["kpi_id"] == "KPI-PERF-002")
    assert not queued["improved"]  # the auto-suspend change does not touch queueing

    rec = store.get("obs_value_measurement", suggestion_id="SUG-0142")
    assert rec["outcome"] == "value_realised" and float(rec["realised_usd"]) == pytest.approx(realised["annualised_usd"])
    assert float(rec["identified_usd"]) == 84000
    w = windows(IMPLEMENTED, default_rubrics())
    assert rec["before_end"] < IMPLEMENTED <= rec["after_start"] and rec["after_end"] == w["after_end"]
    kpi_results = json.loads(rec["kpi_results"])
    assert {k["kpi_id"] for k in kpi_results} == {"KPI-COST-007", "KPI-PERF-002"}
    assert current_status(store, "SUG-0142") == "value_realised"
    transition = store.get("obs_suggestion_status", suggestion_id="SUG-0142")
    assert transition["from_status"] == "implemented" and transition["measurement_id"] == rec["measurement_id"]
    assert store.query("SELECT * FROM audit_event WHERE subject_id = 'SUG-0142'")


def test_no_improvement_and_insufficient_data_keep_status(measured):
    store, out = measured
    assert out["SUG-0150"]["status"] == "implemented"
    assert out["SUG-0150"]["value"]["realised"]["outcome"] == "no_improvement"
    assert out["SUG-0151"]["value"]["realised"]["outcome"] == "insufficient_data"  # after window not complete yet
    assert out["SUG-0160"]["status"] == "proposed" and "realised" not in out["SUG-0160"]["value"]
    assert current_status(store, "SUG-0150") is None


def test_measurement_is_deterministic_and_idempotent(obs_fixed, measured):
    store, out = measured
    again = measure_suggestions(obs_fixed, SUGGESTIONS, store=store, tenant_id="TEN-EXAMPLE")
    assert {s["id"]: s.get("measurement") for s in again} == {k: v.get("measurement") for k, v in out.items()}
    assert store.scalar("SELECT count(*) FROM obs_value_measurement") == 3
    assert store.scalar("SELECT count(*) FROM obs_suggestion_status") == 1


def test_value_records_are_append_only(measured):
    store, _ = measured
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE obs_value_measurement SET realised_usd = 1")
    with pytest.raises(AppendOnlyViolation):
        store.execute("DELETE FROM obs_suggestion_status")


def test_qbr_summary_identified_vs_realised_and_health_delta(obs_fixed, measured):
    store, out = measured
    qbr = qbr_summary(obs_fixed, list(out.values()), store=store, tenant_id="TEN-EXAMPLE")
    assert qbr["identified_usd"] == 84000 + 12000 + 0 + 9000
    assert qbr["realised_usd"] == pytest.approx(out["SUG-0142"]["value"]["realised"]["annualised_usd"])
    assert qbr["by_status"] == {"implemented": 2, "proposed": 1, "value_realised": 1}
    hi = qbr["health_index"]
    assert hi["baseline"] is not None and hi["current"] is not None and hi["delta"] == pytest.approx(
        hi["current"] - hi["baseline"], abs=0.02)
    assert hi["pillars_after"]["cost_optimization"] > hi["pillars_before"]["cost_optimization"]
    assert store.get("obs_qbr_summary", qbr_id=qbr["qbr_id"])
    with_baseline = qbr_summary(obs_fixed, list(out.values()), baseline_health_index=40.0)
    assert with_baseline["health_index"]["baseline_source"] == "package_d"
    assert with_baseline["health_index"]["delta"] == pytest.approx(hi["current"] - 40.0, abs=0.01)
