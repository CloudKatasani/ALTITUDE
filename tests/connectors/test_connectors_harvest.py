"""Acceptance (M2): harvesting a sample database populates objects, dependencies and usage —
read-only, within the permission manifest, metadata only (never user-table rows)."""

import json
from collections import Counter

import pytest

from altitude.core.errors import ReadOnlyViolation
from altitude.core.snapshot import Snapshot
from altitude.core.store import Store
from altitude_connectors import ExtractionAgent, assert_metadata_only
from altitude_connectors.agent import EgressViolation
from altitude_connectors.canonical import CANONICAL_TABLES
from altitude_connectors.harvest import SqlServerHarvester
from altitude_connectors.manifest import load_manifest


def _edge(bundle, src, kind, dst):
    ids = {o["fq_name"]: o["object_id"] for o in bundle.objects}
    return {"from_object_id": ids[src], "to_object_id": ids[dst], "kind": kind} in [
        {k: e[k] for k in ("from_object_id", "to_object_id", "kind")} for e in bundle.edges]


def _obj(bundle, fq):
    return bundle.object_by_name(fq)


def test_sqlserver_harvest_populates_objects(mssql_bundle):
    b = mssql_bundle
    types = Counter(o["object_type"] for o in b.objects)
    assert len(b.objects) >= 60
    assert types["table"] == 28 and types["view"] == 12 and types["procedure"] == 14
    assert types["function"] == 3 and types["trigger"] == 1 and types["schedule"] == 5 and types["etl_job"] == 3
    assert _obj(b, "SalesDW.dbo.sysdiagrams") is None  # is_ms_shipped objects are excluded
    proc = _obj(b, "SalesDW.etl.usp_LoadDimProduct")
    assert proc["loc"] > 20 and proc["code_hash"]
    text = next(v["source_text"] for v in b.versions if v["object_id"] == proc["object_id"])
    assert "CURSOR LOCAL FAST_FORWARD" in text
    assert b.source_system["version"] == "16.0.4135.4"
    cols = [c for c in b.columns if c["object_id"] == _obj(b, "SalesDW.dbo.DimCustomer")["object_id"]]
    assert [c["column_name"] for c in cols][:2] == ["CustomerKey", "CustomerCode"]
    assert cols[1]["data_type"] == "nvarchar(20)" and cols[1]["attributes"]["collation"].endswith("_CI_AS")
    attrs = {(a["object_id"], a["attr"]): a["value"] for a in b.attributes}
    assert attrs[(_obj(b, "SalesDW.dbo.FactSales")["object_id"], "row_count")] == "250000000"
    assert attrs[(_obj(b, "msdb.job.Month End Close")["object_id"], "schedule_frequency")] == "monthly"
    assert attrs[(_obj(b, "SSISDB.DW.Staging.LoadProducts.dtsx")["object_id"], "script_tasks")] == "1"
    assert {g["grantee"] for g in b.grants} >= {"bi_readers", "analysts", "etl_svc", "app_user"}
    assert not any(g["object_fq_name"] == "SalesDW.dbo.DimEmployee" for g in b.grants)  # DENY is not a grant


def test_sqlserver_harvest_populates_dependencies(mssql_bundle):
    b = mssql_bundle
    # view chain (nested views) and function call from catalog dependencies
    assert _edge(b, "SalesDW.rpt.vw_ExecDashboard", "reads", "SalesDW.dbo.vw_SalesSummaryRegion")
    assert _edge(b, "SalesDW.dbo.vw_SalesSummaryRegion", "reads", "SalesDW.dbo.vw_SalesSummary")
    assert _edge(b, "SalesDW.dbo.vw_SalesSummary", "reads", "SalesDW.dbo.vw_SalesBase")
    assert _edge(b, "SalesDW.dbo.vw_SalesBase", "reads", "SalesDW.dbo.FactSales")
    assert _edge(b, "SalesDW.dbo.vw_SalesSummaryRegion", "calls", "SalesDW.dbo.fn_GetRegion")
    # procedure lineage: reads vs writes vs calls
    assert _edge(b, "SalesDW.etl.usp_LoadFactSales", "writes", "SalesDW.dbo.FactSales")
    assert _edge(b, "SalesDW.etl.usp_LoadFactSales", "reads", "SalesDW.stg.Sales_Load")
    assert _edge(b, "SalesDW.etl.usp_LoadFactSales", "calls", "SalesDW.etl.usp_LogLoad")
    # comma join seen only by sys.sql_expression_dependencies
    assert _edge(b, "SalesDW.rpt.vw_ProductMargin", "reads", "SalesDW.dbo.Promotion")
    # schedulers and ETL
    assert _edge(b, "msdb.job.Nightly DW Load", "schedules", "SalesDW.etl.usp_LoadFactSales")
    assert _edge(b, "msdb.job.SSIS Staging Load", "schedules", "SSISDB.DW.Staging.LoadStaging.dtsx")
    assert _edge(b, "SSISDB.DW.Staging.LoadStaging.dtsx", "writes", "SalesDW.stg.Sales_Load")
    assert _edge(b, "SalesDW.dbo.trg_FactSales_Audit", "writes", "SalesDW.audit.SalesAudit")
    # dynamic SQL is invisible to static lineage (MS-06) — recorded, not guessed
    assert not _edge(b, "SalesDW.etl.usp_RegulatoryFiling", "writes", "SalesDW.rpt.RegulatoryFiling")
    attrs = {(a["object_id"], a["attr"]): a["value"] for a in b.attributes}
    unresolved = json.loads(attrs[(_obj(b, "SalesDW.dbo.usp_RefreshExchangeRates")["object_id"], "unresolved_refs")])
    assert "fxsrv.treasury.dbo.dailyrates" in unresolved


def test_sqlserver_harvest_populates_usage(mssql_bundle):
    b = mssql_bundle
    by = {o["fq_name"]: o for o in b.objects}
    assert by["SalesDW.rpt.vw_SalesByRegion"]["usage_90d"] > 100
    assert by["SalesDW.dbo.usp_GetCustomerOrders"]["usage_90d"] == 5400
    assert by["msdb.job.Nightly DW Load"]["usage_90d"] >= 90
    assert by["SSISDB.DW.Staging.LoadStaging.dtsx"]["usage_90d"] >= 90
    assert by["SalesDW.dbo.fn_FiscalQuarter"]["usage_90d"] > 0  # Query Store module statements
    assert by["SalesDW.dbo.vw_LegacyBudget"]["usage_90d"] == 0 and by["SalesDW.dbo.vw_LegacyBudget"]["last_used_at"] is None
    dormant = by["SalesDW.rpt.vw_ProductMargin"]
    assert dormant["usage_90d"] == 0 and dormant["last_used_at"].year == 2026 and dormant["last_used_at"].month == 4
    rows = [u for u in b.usage if u["object_id"] == by["SalesDW.rpt.vw_SalesByRegion"]["object_id"]]
    assert len(rows) >= 12 and all(r["period_end"] >= r["period_start"] for r in rows)
    ssis = [u for u in b.usage if u["object_id"] == by["SSISDB.DW.Staging.LoadStaging.dtsx"]["object_id"]]
    assert all(u["distinct_users"] == 1 for u in ssis)


def test_plan_cache_fallback_when_query_store_is_off(mssql):
    agent = ExtractionAgent("sqlserver", mssql.build(query_store=False), engagement_id="ENG-T", system_name="SalesDW",
                            execute_dialect="duckdb", as_of=mssql.AS_OF)
    b = agent.harvest()
    assert "usage source: plan_cache" in b.meta["notes"]
    assert any("CROSS APPLY" in e.sql for e in agent.statement_log.entries)
    by = {o["fq_name"]: o for o in b.objects}
    assert by["SalesDW.rpt.vw_SalesByRegion"]["usage_90d"] > 0
    assert by["SalesDW.dbo.vw_LegacyBudget"]["last_used_at"] is None


def test_harvest_never_ships_row_data(mssql, mssql_bundle, tmp_path):
    # the emulated source really holds user rows with canary values ...
    raw = mssql.build()
    assert raw.execute("SELECT count(*) FROM dbo.DimCustomer WHERE CustomerName LIKE 'CANARY%'").fetchone()[0] == 2
    # ... and none of them (nor literals from query text) appear anywhere in what the agent ships
    payload = mssql_bundle.to_json()
    assert mssql.CANARY not in payload and mssql.CANARY_QUERY_LITERAL not in payload
    snap = mssql_bundle.to_snapshot(tmp_path)
    dump = json.dumps([snap.query(f'SELECT * FROM "{t}"') for t in snap.tables()], default=str)
    assert mssql.CANARY not in dump and mssql.CANARY_QUERY_LITERAL not in dump
    # only canonical tables and only catalog objects were read
    assert set(snap.tables()) == set(CANONICAL_TABLES)
    scope = {s.lower() for s in load_manifest("sqlserver").scope}
    for s in mssql_bundle.statements:
        assert {o.lower() for o in s["objects"].split(",") if o} <= scope


def test_harvester_cannot_read_user_tables_even_if_it_tries(mssql):
    class GreedyHarvester(SqlServerHarvester):
        def collect(self):
            super().collect()
            self.q("SELECT CustomerName FROM dbo.DimCustomer")

    h = GreedyHarvester(mssql.build(), engagement_id="ENG-T", system_name="SalesDW", execute_dialect="duckdb",
                        as_of=mssql.AS_OF)
    with pytest.raises(ReadOnlyViolation, match="objects_read"):
        h.harvest()
    assert h.conn.log.refused()[0].sql == "SELECT CustomerName FROM dbo.DimCustomer"


def test_egress_guard_rejects_non_metadata(mssql_bundle):
    manifest = load_manifest("sqlserver")
    assert_metadata_only(mssql_bundle, manifest)
    import copy

    tampered = copy.deepcopy(mssql_bundle)
    tampered.objects[0]["sample_rows"] = ["x"]
    with pytest.raises(EgressViolation):
        assert_metadata_only(tampered, manifest)
    tampered = copy.deepcopy(mssql_bundle)
    table = next(o for o in tampered.objects if o["object_type"] == "table")
    tampered.versions.append({"object_id": table["object_id"], "code_hash": "x", "source_text": "1,Jane", "harvested_at": None})
    with pytest.raises(EgressViolation):
        assert_metadata_only(tampered, manifest)
    tampered = copy.deepcopy(mssql_bundle)
    tampered.statements.append({"seq": 999, "verdict": "allowed", "reason": None, "objects": "dbo.DimCustomer",
                                "row_count": 1, "statement": "SELECT * FROM dbo.DimCustomer"})
    with pytest.raises(EgressViolation):
        assert_metadata_only(tampered, manifest)


def test_harvest_is_deterministic_and_seals_into_snapshot_and_store(mssql, mssql_agent, tmp_path):
    again = ExtractionAgent("sqlserver", mssql.build(), engagement_id="ENG-T", system_name="SalesDW",
                            script_dirs=[mssql.SSIS_DIR], execute_dialect="duckdb", as_of=mssql.AS_OF).harvest()
    assert again.content_hash() == mssql_agent.bundle.content_hash()
    store = Store()
    snap = mssql_agent.ship(snapshot_dir=tmp_path, store=store)
    Snapshot.open(snap.path, verify=True)
    assert snap.manifest["kind"] == "harvest" and snap.metadata["as_of"] == mssql.AS_OF.isoformat()
    assert snap.scalar("SELECT count(*) FROM source_object") == len(mssql_agent.bundle.objects)
    assert store.scalar("SELECT count(*) FROM source_object") == len(mssql_agent.bundle.objects)
    assert store.scalar("SELECT count(*) FROM dependency_edge") == len(mssql_agent.bundle.edges)
    assert store.scalar("SELECT count(*) FROM usage_stat") == len(mssql_agent.bundle.usage)
    assert store.scalar('SELECT count(*) FROM "grant"') == len(mssql_agent.bundle.grants)
    run = store.all("harvest_run")[0]
    assert run["snapshot_id"] == snap.snapshot_id and run["refused"] == 0
    assert store.get("snapshot", snapshot_id=snap.snapshot_id)
    mssql_agent.bundle.to_store(store)  # re-harvest replaces, never duplicates
    assert store.scalar("SELECT count(*) FROM source_object") == len(mssql_agent.bundle.objects)


def test_oracle_harvest(ora):
    agent = ExtractionAgent("oracle", ora.build(), engagement_id="ENG-T", system_name="ORAPROD",
                            execute_dialect="duckdb", as_of=ora.AS_OF)
    b = agent.harvest()
    types = Counter(o["object_type"] for o in b.objects)
    assert types["table"] == 12 and types["view"] == 4 and types["package"] == 2 and types["schedule"] == 2
    assert _obj(b, "SYS.DBMS_OUTPUT") is None and _obj(b, "SALES.ORDERS_SEQ") is None
    pkg = _obj(b, "SALES.SALES_PKG")
    text = next(v["source_text"] for v in b.versions if v["object_id"] == pkg["object_id"])
    assert text.startswith("CREATE OR REPLACE PACKAGE SALES.SALES_PKG") and "PACKAGE BODY" in text
    assert _edge(b, "SALES.SALES_PKG", "writes", "SALES.DAILY_SALES_AGG")
    assert _edge(b, "SALES.SALES_PKG", "reads", "SALES.ORDER_LINES")  # (+) join seen via DBA_DEPENDENCIES
    assert _edge(b, "SALES.V_SALES_BY_MONTH", "reads", "SALES.V_CUSTOMER_ORDERS")
    assert _edge(b, "SCHEDULER.SALES.LOAD_DAILY_JOB", "schedules", "SALES.SALES_PKG")
    assert _edge(b, "SCHEDULER.FIN.MONTH_END_CLOSE", "schedules", "FIN.GL_CLOSE_PKG")
    by = {o["fq_name"]: o for o in b.objects}
    assert by["SALES.V_SALES_BY_MONTH"]["usage_90d"] > 0
    users = [u["distinct_users"] for u in b.usage if u["object_id"] == by["SALES.V_SALES_BY_MONTH"]["object_id"]]
    assert max(users) == 3
    attrs = {(a["object_id"], a["attr"]): a["value"] for a in b.attributes}
    assert attrs[(by["SCHEDULER.FIN.MONTH_END_CLOSE"]["object_id"], "month_end")] == "True"
    cols = {c["column_name"]: c for c in b.columns if c["object_id"] == by["SALES.ORDERS"]["object_id"]}
    assert cols["ORDER_ID"]["attributes"]["unscaled_number"] is True  # OR-02 signal
    assert cols["ORDER_DATE"]["attributes"]["has_time_component"] is True  # OR-03 signal
    assert {g["grantee_type"] for g in b.grants} == {"role", "user"}
    assert ora.CANARY not in b.to_json()


def test_teradata_harvest_with_bteq_scripts(td):
    agent = ExtractionAgent("teradata", td.build(), engagement_id="ENG-T", system_name="TDPROD",
                            execute_dialect="duckdb", as_of=td.AS_OF, script_dirs=[td.BTEQ_DIR])
    b = agent.harvest()
    types = Counter(o["object_type"] for o in b.objects)
    assert types["table"] == 8 and types["view"] == 4 and types["macro"] == 1 and types["script"] == 3
    assert _edge(b, "bteq:load_sales.bteq", "writes", "EDW.SALES_FACT")
    assert _edge(b, "bteq:load_sales.bteq", "calls", "EDW.M_REFRESH_AGG")
    assert _edge(b, "EDW.M_REFRESH_AGG", "writes", "EDW.SALES_DAILY_AGG")
    assert _edge(b, "EDW_V.V_SALES_MONTHLY", "reads", "EDW_V.V_SALES")
    by = {o["fq_name"]: o for o in b.objects}
    assert by["bteq:load_sales.bteq"]["usage_90d"] > 0  # from DBQL query bands
    assert by["bteq:legacy_extract.bteq"]["usage_90d"] == 0
    assert by["EDW.OLD_SALES_2016"]["last_used_at"] is None
    payload = b.to_json()
    assert "S3cr3tPassw0rd" not in payload and "0ldPassw0rd" not in payload and ".LOGON <redacted>" in payload
    assert td.CANARY not in payload
    attrs = {(a["object_id"], a["attr"]): a["value"] for a in b.attributes}
    assert attrs[(by["EDW.CUSTOMER"]["object_id"], "table_kind")] == "SET"  # TD-01 signal
    assert attrs[(by["EDW.SALES_FACT"]["object_id"], "size_bytes")] == str(1_400_000_000_000)
    name = next(c for c in b.columns if c["object_id"] == by["EDW.CUSTOMER"]["object_id"]
                and c["column_name"] == "CUSTOMER_NAME")
    assert name["attributes"] == {"casespecific": False}  # TD-02 signal
    seg = next(c for c in b.columns if c["object_id"] == by["EDW.CUSTOMER"]["object_id"] and c["column_name"] == "SEGMENT")
    assert seg["attributes"] == {"casespecific": True, "char_padded": True}  # TD-03 signal
