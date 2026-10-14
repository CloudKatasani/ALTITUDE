"""Alerts & runbooks as data: a seeded anomaly fires the right alert to the right route with the right runbook."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from altitude.observability.alerts import evaluate_alerts, forecast_band
from altitude.observability.config import load_alerts, load_kpis, load_registry, load_runbooks, resolve_route
from altitude.observability.routing import build_payload, routing_test, routing_test_due



def _credit(events):
    return [e for e in events if e["ALERT_CLASS"] == "credit_anomaly"]


def test_catalogue_covers_section_7_6_and_references_resolve():
    cat = load_alerts()
    classes = {a["class"] for a in cat["alerts"]}
    assert {"credit_anomaly", "budget_breach", "tier1_task_failure", "freshness_breach", "accountadmin_use",
            "new_user_without_mfa", "masking_gap", "cortex_spend_spike", "signature_regression"} <= classes
    runbooks = load_runbooks()
    kpis = {k["id"]: k for k in load_kpis()}
    reg = load_registry()
    for a in cat["alerts"]:
        assert a["runbook"] in runbooks and a["class"] in runbooks[a["runbook"]]["alert_classes"]
        assert kpis[a["kpi"]]["status"] == "implemented"
        name, route = resolve_route(reg, a["route_ref"])
        assert route["channel"] in {"slack", "teams", "pagerduty", "servicenow"}
        assert a["owner_role"] and a["severity"] in cat["severities"] and a["suppression_hours"] >= 0
    for k in kpis.values():  # KPI-embedded alert blocks point at real runbooks and routes
        if k.get("alert"):
            assert k["alert"]["runbook"] in runbooks
            resolve_route(reg, k["alert"]["route_ref"])


def test_seeded_anomaly_fires_the_credit_anomaly_alert_to_finops(obs_anomaly, tmp_path):
    day = date(2026, 9, 29)
    events = evaluate_alerts(obs_anomaly, load_registry(), day, tmp_path, accounts=["ACME_PROD"])
    fired = _credit(events)
    assert [(e["DIMENSION"], e["STATUS"]) for e in fired] == [("WH_DS", "fired")]
    e = fired[0]
    assert e["ALERT_ID"] == "ALR-COST-ANOMALY" and e["SEVERITY"] == "high"
    assert e["ROUTE"] == "finops" and e["CHANNEL"] == "slack" and e["RUNBOOK"] == "RB-COST-ANOMALY"
    assert e["OBSERVED"] > e["UPPER_BAND"] > e["EXPECTED"]
    payload = json.loads(Path(e["OUTBOX_PATH"]).read_text())
    assert Path(e["OUTBOX_PATH"]).parent.name == "slack"
    assert payload["channel"] == "#finops-alerts"
    assert "RB-COST-ANOMALY" in json.dumps(payload) and "WH_DS" in payload["text"]
    stored = obs_anomaly.query("SELECT * FROM OPS.ALERT_EVENT WHERE ALERT_ID = 'ALR-COST-ANOMALY'")
    assert len(stored) == 1 and stored[0]["DIMENSION"] == "WH_DS"


@pytest.mark.parametrize("day", [date(2026, 9, 28), date(2026, 9, 30), date(2026, 9, 26)])
def test_normal_days_do_not_fire_a_credit_anomaly(obs_anomaly, tmp_path, day):
    events = evaluate_alerts(obs_anomaly, load_registry(), day, tmp_path, accounts=["ACME_PROD"],
                             alert_ids=["ALR-COST-ANOMALY"])
    assert _credit(events) == []
    assert not (tmp_path / "slack").exists()


def test_evaluation_is_idempotent_and_repeats_are_suppressed(obs_seeded, tmp_path):
    reg = load_registry()
    d1 = date(2026, 9, 28)
    first = evaluate_alerts(obs_seeded, reg, d1, tmp_path, accounts=["ACME_PROD"], alert_ids=["ALR-GOV-MASKING-GAP"])
    assert [(e["DIMENSION"], e["STATUS"], e["CHANNEL"], e["RUNBOOK"]) for e in first] == [
        ("EDW.SALES.DIM_CUSTOMER.EMAIL", "fired", "servicenow", "RB-GOV-MASKING-GAP")]
    again = evaluate_alerts(obs_seeded, reg, d1, tmp_path, accounts=["ACME_PROD"], alert_ids=["ALR-GOV-MASKING-GAP"])
    assert [e["EVENT_ID"] for e in again] == [e["EVENT_ID"] for e in first]
    nxt = evaluate_alerts(obs_seeded, reg, d1 + timedelta(days=1), tmp_path, accounts=["ACME_PROD"],
                          alert_ids=["ALR-GOV-MASKING-GAP"])
    assert [e["STATUS"] for e in nxt] == ["suppressed"]  # inside the 168h suppression window
    assert obs_seeded.scalar("SELECT count(*) FROM OPS.ALERT_EVENT WHERE ALERT_ID = 'ALR-GOV-MASKING-GAP'") == 2
    snow = json.loads(Path(first[0]["OUTBOX_PATH"]).read_text())
    assert snow["table"] == "incident" and snow["record"]["assignment_group"] == "Security Operations"
    assert snow["record"]["impact"] == 2 and snow["record"]["correlation_id"] == first[0]["EVENT_ID"]


def test_seeded_profile_fires_security_alerts_but_clean_does_not(obs_seeded, obs_anomaly, tmp_path):
    reg = load_registry()
    day = date(2026, 9, 30)
    seeded = {e["ALERT_ID"] for e in evaluate_alerts(obs_seeded, reg, day, tmp_path / "s", accounts=["ACME_PROD"])}
    assert {"ALR-SEC-ACCOUNTADMIN", "ALR-REL-FRESHNESS"} <= seeded
    clean = {e["ALERT_ID"] for e in evaluate_alerts(obs_anomaly, reg, day, tmp_path / "c", accounts=["ACME_PROD"])}
    assert not clean & {"ALR-SEC-ACCOUNTADMIN", "ALR-GOV-MASKING-GAP", "ALR-REL-FRESHNESS", "ALR-COST-ANOMALY"}


def test_forecast_band_needs_history_and_uses_rubric_band():
    from altitude.core.rubric import default_rubrics

    rs = default_rubrics()
    rule = load_alerts()["alerts"][0]["rule"]
    assert forecast_band([10.0], rs, rule) is None
    exp, upper = forecast_band([10.0, 10.0, 10.0, 10.0], rs, rule)
    assert exp == 10.0 and upper == pytest.approx(10.0 * (1 + rs.get("rubric.obs.anomaly.min_band_pct")))


def test_payload_builders_for_every_channel():
    event = {"EVENT_ID": "ALE-1", "ALERT_ID": "ALR-X", "ALERT_CLASS": "credit_anomaly", "ALERT_NAME": "Credit anomaly",
             "SEVERITY": "critical", "ACCOUNT_NAME": "ACME_PROD", "DIMENSION": "WH_DS", "EVALUATED_FOR": "2026-09-29",
             "MESSAGE": "spike", "RUNBOOK": "RB-COST-ANOMALY", "OWNER_ROLE": "FINOPS_LEAD"}
    pd = build_payload(event, {"channel": "pagerduty", "target": "oncall", "routing_key_ref": "vault://x"})
    assert pd["event_action"] == "trigger" and pd["payload"]["severity"] == "critical"
    assert pd["dedup_key"] == "ALR-X:ACME_PROD:WH_DS"
    teams = build_payload(event, {"channel": "teams", "target": "Platform"})
    assert teams["@type"] == "MessageCard" and any(f["value"] == "RB-COST-ANOMALY" for f in teams["sections"][0]["facts"])
    slack = build_payload(event, {"channel": "slack", "target": "#x"})
    assert slack["blocks"][0]["type"] == "header"
    with pytest.raises(ValueError):
        build_payload(event, {"channel": "carrier-pigeon", "target": "x"})


def test_monthly_routing_test(tmp_path, obs_anomaly):
    reg = load_registry()
    day = date(2026, 9, 30)
    results = routing_test(obs_anomaly, reg, tmp_path, day)
    routes = {a["route_ref"] for a in load_alerts()["alerts"]}
    assert {r["ROUTE"] for r in results} == routes and all(r["OK"] for r in results)
    for r in results:
        assert json.loads(Path(r["OUTBOX_PATH"]).read_text())["test"] is True
    assert not routing_test_due(obs_anomaly, day + timedelta(days=7))
    assert routing_test_due(obs_anomaly, day + timedelta(days=40))
    broken = {**reg, "alert_routes": {k: v for k, v in reg["alert_routes"].items() if k != "dataops"}}
    res = routing_test(obs_anomaly, broken, tmp_path / "b", day + timedelta(days=1))
    assert [r["ROUTE"] for r in res if not r["OK"]] == ["tenant.alert_routes.dataops"]
