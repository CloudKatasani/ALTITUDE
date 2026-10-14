"""Dashboards (1, 2, 4, 8), generated Snowflake artifacts and the ``altitude obs`` CLI."""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from altitude.cli import main
from altitude.core.generated import is_stamped
from altitude.observability.config import kpi_table, load_registry
from altitude.observability.dashboards import chargeback_statements, render_dashboards
from altitude.observability.generate import agent_spec, generate
from altitude.observability.kpi import implemented


@pytest.fixture(scope="module")
def dashboards(obs_seeded, tmp_path_factory):
    out = tmp_path_factory.mktemp("dash")
    return out, render_dashboards(obs_seeded, out, value_summary={
        "identified_usd": 96000, "realised_usd": 50000,
        "items": [{"id": "SUG-1", "check_id": "DX-COST-01", "status": "value_realised", "identified_usd": 84000,
                   "realised_usd": 50000}]})


def test_dashboards_render_from_kpi_tables(dashboards):
    out, paths = dashboards
    names = {Path(p).relative_to(out).as_posix() for p in paths}
    assert {"executive_cost_value.html", "platform_health.html", "pipelines_freshness.html",
            "chargeback/index.html"} <= names
    assert len([n for n in names if n.startswith("chargeback/2026-09_")]) >= 4
    for p in paths:
        text = Path(p).read_text()
        assert "{{" not in text and "}}" not in text, p
        assert "ALTITUDE" in text  # product name came from the default theme token
    exec_ = (out / "executive_cost_value.html").read_text()
    assert exec_.count("<svg") >= 3 and "KPI-COST-003" in exec_ and "Value realised" in exec_
    health = (out / "platform_health.html").read_text()
    assert "Platform Health Index" in health and "KPI-PHI-002" in health and 'class="rag red"' in health
    pipes = (out / "pipelines_freshness.html").read_text()
    assert "EDW.FINANCE.FCT_REVENUE" in pipes and "KPI-REL-003" in pipes


def test_dashboards_are_white_label(obs_seeded, tmp_path):
    paths = render_dashboards(obs_seeded, tmp_path, theme="partner_example")
    for p in paths:
        text = Path(p).read_text()
        assert "ALTITUDE" not in text and "Sherpa" not in text
    assert "Summit Insight" in (tmp_path / "platform_health.html").read_text()
    assert "Estate Health Index" in (tmp_path / "platform_health.html").read_text()


def test_chargeback_statements_sum_to_the_bill(obs_seeded):
    month = date(2026, 9, 1)
    docs = chargeback_statements(obs_seeded, month, load_registry(), None)
    statements = {k: v for k, v in docs.items() if not k.endswith("index.html")}
    totals = []
    for text in statements.values():
        m = re.search(r'<tr class="total">.*?\$([\d,]+)</td></tr>', text, re.S)
        totals.append(float(m.group(1).replace(",", "")))
    billed = obs_seeded.scalar("SELECT sum(VALUE) FROM KPI.KPI_COST_011 WHERE PERIOD BETWEEN '2026-09-01' AND '2026-09-30'")
    assert abs(sum(totals) - billed) <= len(totals)  # rounding to whole dollars per statement
    assert "finance-bi@example.com" in docs["chargeback/2026-09_finance_bi.html"]
    assert "UNALLOCATED" in docs["chargeback/index.html"]


def test_generated_artifacts_are_stamped_deterministic_and_complete():
    a, b = generate(), generate()
    assert a == b
    for rel, text in a.items():
        assert rel.startswith("observability/") and is_stamped(text), rel
    names = set(a)
    for f in ["snowflake/00_database.sql", "snowflake/01_raw_tables.sql", "snowflake/02_grants.sql",
              "snowflake/03_curated.sql", "snowflake/04_kpi_dynamic_tables.sql", "snowflake/05_semantic.sql",
              "snowflake/06_alerts.sql", "cortex/ask_the_platform_agent.json", "cortex/create_agent.sql",
              "streamlit/streamlit_app.py", "alerts/alert_catalogue.json"]:
        assert f"observability/{f}" in names
    dts = a["observability/snowflake/04_kpi_dynamic_tables.sql"]
    for k in implemented(engine="sql"):
        assert f"CREATE OR REPLACE DYNAMIC TABLE OBS.KPI.{kpi_table(k['id'])}\n" in dts
    sem = a["observability/snowflake/05_semantic.sql"]
    assert sem.count("CREATE OR REPLACE SEMANTIC VIEW") == len({k["domain"] for k in implemented()})
    alerts = a["observability/snowflake/06_alerts.sql"]
    assert alerts.count("CREATE OR REPLACE ALERT") == 10 and "$account" not in alerts and "$day" not in alerts
    compile(a["observability/streamlit/streamlit_app.py"], "streamlit_app.py", "exec")
    spec = json.loads(a["observability/cortex/ask_the_platform_agent.json"])
    assert spec["tool_resources"] and all(v["semantic_view"].startswith("OBS.SEMANTIC.SV_")
                                          for v in spec["tool_resources"].values())
    assert len(agent_spec()["instructions"]["sample_questions"]) >= 10


def test_cli_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "obs.duckdb")
    assert main(["obs", "harvest", "--db", db, "--as-of", "2026-09-30", "--days", "14", "--retention-days", "14"]) == 0
    harvested = json.loads(capsys.readouterr().out)
    assert {h["account"] for h in harvested} == {"ACME_PROD", "ACME_DEV"}
    assert main(["obs", "kpis", "--db", db]) == 0
    assert json.loads(capsys.readouterr().out)["kpis"] >= 55
    assert main(["obs", "reconcile", "--db", db]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert main(["obs", "alerts", "--db", db, "--date", "2026-09-30", "--outbox", str(tmp_path / "outbox")]) == 0
    alerts = json.loads(capsys.readouterr().out)
    assert alerts["events"] and alerts["routing_test"]
    assert main(["obs", "ask", "--db", db, "What is our MFA coverage for ACME_DEV?"]) == 0
    assert "KPI-SEC-001" in capsys.readouterr().out
    assert main(["obs", "ask", "--db", db, "--json", "What is the meaning of life?"]) == 2
    assert json.loads(capsys.readouterr().out)["answered"] is False
    sugg = tmp_path / "s.json"
    sugg.write_text(json.dumps([{"id": "SUG-1", "check_id": "DX-COST-01", "kpis_to_watch": ["KPI-COST-007"],
                                 "status": "implemented", "implemented_at": "2026-09-22", "account_name": "ACME_PROD",
                                 "value": {"annualised_usd": {"p50": 1000}}}]))
    assert main(["obs", "value", "--db", db, "--suggestions", str(sugg), "--account", "ACME_PROD",
                 "--out", str(tmp_path / "qbr.json")]) == 0
    assert json.loads(capsys.readouterr().out)["identified_usd"] == 1000
    assert main(["obs", "dashboards", "--db", db, "--out", str(tmp_path / "dash"), "--account", "ACME_PROD",
                 "--value-summary", str(tmp_path / "qbr.json")]) == 0
    assert (tmp_path / "dash" / "executive_cost_value.html").exists()
    assert main(["obs", "freshness", "--db", db, "--as-of", "2026-10-01"]) == 0
