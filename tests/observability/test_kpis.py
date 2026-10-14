"""KPI catalogue as data, KPI computation, Health Index and cost reconciliation to billing."""

from datetime import date

import pytest
import sqlglot

from altitude.core.rubric import default_rubrics
from altitude.observability.config import kpi_table, load_kpis
from altitude.observability.curate import curated_objects, rubric_placeholders, substitute_rubric
from altitude.observability.kpi import implemented, kpi_select
from altitude.observability.reconcile import reconcile

from altitude.synthetic import AccountSpec

SHARED_IDS = [
    "KPI-COST-001", "KPI-COST-002", "KPI-COST-003", "KPI-COST-004", "KPI-COST-005", "KPI-COST-006", "KPI-COST-007",
    "KPI-COST-008", "KPI-COST-009", "KPI-PERF-001", "KPI-PERF-002", "KPI-PERF-003", "KPI-PERF-004", "KPI-PERF-005",
    "KPI-REL-001", "KPI-REL-002", "KPI-REL-003", "KPI-SEC-001", "KPI-SEC-002", "KPI-SEC-003", "KPI-SEC-004",
    "KPI-SEC-005", "KPI-GOV-001", "KPI-GOV-002", "KPI-GOV-003", "KPI-GOV-004", "KPI-USE-001", "KPI-USE-002",
    "KPI-USE-003", "KPI-AI-001", "KPI-PHI-001",
]


def test_catalogue_shape_and_shared_ids():
    kpis = load_kpis()
    ids = [k["id"] for k in kpis]
    assert len(ids) == len(set(ids))
    assert len(kpis) >= 75
    assert set(SHARED_IDS) <= set(ids)
    core = [k for k in kpis if k["tier"] == "core"]
    assert len(core) >= 20 and all(k["status"] == "implemented" for k in core)
    assert {k["domain"] for k in core} >= {"cost", "performance", "reliability", "security", "governance", "usage", "ai"}
    assert len(implemented(kpis)) >= 55
    assert any(k["status"] == "planned" for k in kpis)
    # every shared id except the planned/diagnostics-fed Health Index is implemented
    for kid in SHARED_IDS:
        k = next(x for x in kpis if x["id"] == kid)
        assert k["status"] == "implemented", kid


def test_kpi_sql_and_curated_sql_transpile_to_snowflake_and_rubric_placeholders_resolve():
    rs = default_rubrics()
    for k in implemented(engine="sql"):
        for ref in rubric_placeholders(k["sql"]):
            assert rs.has(ref), (k["id"], ref)
        sqlglot.transpile(kpi_select(k), read="duckdb", write="snowflake")
    for name, sql, sf, _ in curated_objects():
        sqlglot.transpile(substitute_rubric(sql), read="duckdb", write="snowflake")


def test_every_implemented_kpi_is_computed_with_the_uniform_shape(obs_seeded):
    db = obs_seeded
    empty = []
    for k in implemented():
        t = kpi_table(k["id"])
        cols = [r["column_name"] for r in db.query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'KPI' AND table_name = ? "
            "ORDER BY ordinal_position", [t])]
        assert cols[:4] == ["ACCOUNT_NAME", "PERIOD", "DIMENSION", "VALUE"], k["id"]
        assert set(k.get("measures", [])) <= set(cols), k["id"]
        if not db.scalar(f'SELECT count(*) FROM KPI."{t}"'):
            empty.append(k["id"])
    assert empty == [], f"implemented KPIs with no rows on the seeded fixture: {empty}"
    # semantic layer exposes certified definitions and values
    assert db.scalar("SELECT count(*) FROM SEMANTIC.KPI_DEFINITIONS WHERE CERTIFIED") == len(implemented())
    assert db.scalar("SELECT count(DISTINCT KPI_ID) FROM SEMANTIC.KPI_VALUES") == len(implemented())
    assert db.relation_exists("SEMANTIC", "SV_COST")


def test_seeded_issues_show_up_in_kpis(obs_seeded):
    db = obs_seeded
    latest = lambda t: db.scalar(f"SELECT VALUE FROM KPI.{t} ORDER BY PERIOD DESC LIMIT 1")  # noqa: E731
    assert latest("KPI_SEC_001") < 1.0          # DX-SEC-01: humans without MFA
    assert latest("KPI_SEC_002") > 2            # DX-SEC-02: extra ACCOUNTADMIN grantees
    assert latest("KPI_GOV_003") < 1.0          # DX-SEC-05: EMAIL classified but unmasked
    assert latest("KPI_GOV_004") < 1.0          # DX-GOV-02: Tier-1 table without DMF
    assert latest("KPI_SEC_004") >= 1           # DX-SEC-03: dormant user
    idle = db.scalar("SELECT avg(VALUE) FROM KPI.KPI_COST_007 WHERE DIMENSION = 'WH_BI_ADHOC'")
    assert idle > float(default_rubrics().get("rubric.obs.idle_share_alert"))   # DX-COST-01
    spill = db.scalar("SELECT sum(VALUE) FROM KPI.KPI_PERF_003 WHERE DIMENSION = 'WH_ELT_PROD'")
    assert spill > 0                            # DX-PERF-02
    assert db.scalar("SELECT sum(VALUE) FROM KPI.KPI_REL_002") > 0     # DX-REL-01 failing task
    assert db.scalar("SELECT count(*) FROM KPI.KPI_PHI_001") >= 1
    assert db.scalar("SELECT count(DISTINCT DIMENSION) FROM KPI.KPI_PHI_002") == 5


def test_dollar_kpis_are_credits_times_contract_price(obs_seeded):
    db = obs_seeded
    rows = db.query("SELECT a.VALUE AS CREDITS, b.VALUE AS USD, b.PRICE_PER_CREDIT FROM KPI.KPI_COST_001 a "
                    "JOIN KPI.KPI_COST_002 b USING (ACCOUNT_NAME, PERIOD, DIMENSION)")
    assert rows and all(abs(r["CREDITS"] * r["PRICE_PER_CREDIT"] - r["USD"]) < 1e-6 for r in rows)


def test_cost_kpis_reconcile_to_snowflake_billing(obs_seeded):
    r = reconcile(obs_seeded)
    tol = float(default_rubrics().get("rubric.obs.reconciliation.credits_tolerance_pct"))
    assert r["ok"], r["days_failed"][:5]
    assert {m["check"] for m in r["months"]} == {"warehouse", "serverless", "total", "chargeback"}
    for m in r["months"]:
        assert m["billed"] > 0 and m["diff_pct"] <= tol, m
    assert r["days_failed"] == []


def test_reconciliation_detects_a_missing_warehouse(obs_build):
    db = obs_build(AccountSpec(end_date=date(2026, 9, 30), days=10))
    assert reconcile(db)["ok"]
    db.replace_table("KPI", "KPI_COST_001", "SELECT * FROM KPI.KPI_COST_001 WHERE DIMENSION <> 'WH_DS'")
    bad = reconcile(db)
    assert not bad["ok"]
    assert any(m["check"] == "warehouse" and not m["ok"] for m in bad["months"])


@pytest.mark.parametrize("kid", ["KPI-COST-001", "KPI-REL-001", "KPI-SEC-001"])
def test_kpi_tables_are_reproducible(obs_seeded, kid):
    from altitude.observability.kpi import compute_kpis

    t = kpi_table(kid)
    before = obs_seeded.query(f'SELECT * FROM KPI."{t}" ORDER BY ALL')
    compute_kpis(obs_seeded)
    assert obs_seeded.query(f'SELECT * FROM KPI."{t}" ORDER BY ALL') == before
