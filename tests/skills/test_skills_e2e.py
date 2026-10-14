"""End-to-end tests for the Section 17.4 executable skills, called through the shared registry."""

import json
from pathlib import Path

import duckdb
import pytest

from altitude.skills import SkillError, load_skills, run_skill

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
INPUTS = {"deadline_weeks": 40, "appetite_for_change": 3, "model_quality_score": 60, "budget_band": "medium",
          "test_coverage": False, "start_date": "2026-11-02", "regulatory_objects": ["*RegulatoryFiling*"]}

NEW_SKILLS = {
    "run_diagnostic", "harvest_source", "run_assessment", "classify_objects", "recommend_pattern", "plan_waves",
    "estimate_wave", "convert_module", "remediate_ewis", "generate_unit_tests", "generate_dbt_from_mapping",
    "generate_reconciliation_suite", "triage_mismatches", "generate_rbac_from_legacy_grants",
    "run_well_architected_check", "score_ai_readiness", "scan_drift", "ask_the_platform", "run_agent",
}


# ----------------------------------------------------------------------------- registry


def test_every_manifest_resolves_and_is_closed():
    skills = load_skills()
    assert NEW_SKILLS <= set(skills)
    assert all(s.available for s in skills.values()), [s.name for s in skills.values() if not s.available]
    for name in NEW_SKILLS:
        schema = skills[name].input_schema
        assert schema["type"] == "object" and schema["additionalProperties"] is False, name
        assert skills[name].entrypoint.startswith("altitude.skills.impl_"), name


def test_arguments_are_validated(sctx):
    with pytest.raises(SkillError, match="invalid arguments"):
        run_skill("scan_drift", {"sql": "select 1", "dialect": "oracle", "nope": 1}, context=sctx)
    with pytest.raises(SkillError, match="unknown snapshot"):
        run_skill("run_well_architected_check", {"snapshot_id": "SNAP-DOES-NOT-EXIST"}, context=sctx)


# ----------------------------------------------------------------------------- Snowflake estate skills


def test_run_diagnostic(call, sctx, snowflake_snapshot):
    out = call("run_diagnostic", {"snapshot_id": snowflake_snapshot["snapshot_id"], "tier": "D1"})
    assert out["snapshot_id"] == snowflake_snapshot["snapshot_id"] and out["tier"] == "D1"
    assert 0 <= out["platform_health_index"] <= 100
    assert out["suggestions"] > 0 and out["value_p50_usd"] > 0
    assert sum(out["suggestions_by_check"].values()) == out["suggestions"]
    assert sctx.store.get("diag_run", run_id=out["run_id"])["snapshot_id"] == out["snapshot_id"]
    assert out["exports"] and all(Path(p).exists() for p in out["exports"].values())
    sugg = json.loads(Path(out["exports"]["suggestions_json"]).read_text())
    assert len(sugg["suggestions"] if isinstance(sugg, dict) else sugg) == out["suggestions"]
    again = call("run_diagnostic", {"snapshot_id": snowflake_snapshot["path"], "tier": "D1",
                                    "formats": ["findings_csv"]})
    assert again["run_id"] == out["run_id"] and list(again["exports"]) == ["findings_csv"]


def test_run_well_architected_check(call, sctx, snowflake_snapshot):
    out = call("run_well_architected_check", {"snapshot_id": snowflake_snapshot["snapshot_id"]})
    ids = {f["check_id"] for f in out["findings"]}
    assert "WA-IAM-001" in ids  # seeded: human user with password and no MFA
    assert out["rating"] and 0 <= out["overall"] <= 100
    assert all(f["playbook"] for f in out["findings"])
    assert Path(out["report_path"]).read_text().strip()
    assert sctx.store.query("SELECT count(*) AS n FROM wa_finding")[0]["n"] == len(out["findings"])


def test_score_ai_readiness(call, snowflake_snapshot):
    out = call("score_ai_readiness", {"snapshot_id": snowflake_snapshot["snapshot_id"]})
    assert len(out["pillars"]) == 8 and 0 <= out["overall"] <= 100
    assert out["maturity_label"] and out["priorities"]
    again = call("score_ai_readiness", {"snapshot_id": snowflake_snapshot["snapshot_id"]})
    assert again["score_hash"] == out["score_hash"]  # reproducible per snapshot


def test_run_agent(call, sctx, snowflake_snapshot):
    sid = snowflake_snapshot["snapshot_id"]
    with pytest.raises(SkillError, match="has not passed its evaluation suite"):
        call("run_agent", {"agent_id": "AG-WAREHOUSE-RIGHTSIZER", "snapshot_id": sid})
    out = call("run_agent", {"agent_id": "AG-WAREHOUSE-RIGHTSIZER", "snapshot_id": sid, "require_promoted": False})
    assert out["findings"] > 0 and out["actions"]
    assert {a["autonomy"] for a in out["actions"]} <= {"L1", "L2", "L3"}
    executed = [a for a in out["actions"] if a["status"] == "executed"]
    assert len(executed) == len(out["executed_sql"])
    assert all(s.upper().startswith("ALTER WAREHOUSE") for s in out["executed_sql"])
    assert sctx.store.get("agent_run", run_id=out["run_id"])["status"] == "completed"


def test_scan_drift(call):
    out = call("scan_drift", {"sql": "SELECT id FROM customers WHERE middle_name = ''", "dialect": "oracle"})
    assert "OR-01" in out["issues"] and out["summary"]["hits"] == len(out["hits"])
    assert out["hits"][0]["line"] == 1 and out["checklist_flagged"]
    with pytest.raises(SkillError, match="unsupported source dialect"):
        call("scan_drift", {"sql": "select 1", "dialect": "cobol"})


def test_ask_the_platform(call):
    q = "How many credits did WH_DS use in the last 7 days?"
    ans = call("ask_the_platform", {"question": q, "seed_synthetic": {"days": 45, "end_date": "2026-09-30"}})
    assert ans["answered"] and ans["kpi_id"] == "KPI-COST-001" and ans["dimension"] == "WH_DS"
    assert ans["seeded"]["kpis"] > 0 and ans["citations"] and ans["value"] > 0
    refused = call("ask_the_platform", {"question": "What is the capital of France?"})
    assert refused["answered"] is False and refused["seeded"] is None and refused["refusal_reason"]


# ----------------------------------------------------------------------------- source estate skills


def test_harvest_source_sample_and_idempotent(call, sctx, mssql_harvest):
    h = mssql_harvest
    assert h["sample_estate"] and h["counts"]["source_object"] > 0 and h["refused"] == 0
    assert sctx.store.get("snapshot", snapshot_id=h["snapshot_id"])["kind"] == "harvest"
    assert sctx.store.get("source_system", source_system_id=h["source_system_id"])["name"] == "SalesDW"
    again = call("harvest_source", {"source": "sqlserver", "engagement_id": "ENG-SKILLS"})
    assert again["snapshot_id"] == h["snapshot_id"] and again["content_hash"] == h["content_hash"]


def test_harvest_source_from_duckdb_catalog(call, tmp_path, estate_module):
    est = estate_module("teradata")
    path = tmp_path / "tdprod.duckdb"
    con = est.build()
    con.execute(f"ATTACH '{path}' AS exported")
    con.execute("COPY FROM DATABASE memory TO exported")
    con.close()
    out = call("harvest_source", {"source": "teradata", "duckdb_path": str(path), "system_name": "TDPROD",
                                  "engagement_id": "ENG-DUCK", "as_of": est.AS_OF.isoformat()})
    assert out["sample_estate"] is False and out["counts"]["source_object"] > 0 and out["counts"]["grant"] > 0
    with pytest.raises(SkillError, match="does not exist"):
        call("harvest_source", {"source": "teradata", "duckdb_path": str(tmp_path / "missing.duckdb")})


def test_run_assessment_and_classify(call, mssql_harvest, mssql_assessment):
    a = mssql_assessment
    assert a["harvest_snapshot_id"] == mssql_harvest["snapshot_id"]
    assert sum(a["dispositions"].values()) == a["objects"] and a["dispositions"].get("retire", 0) > 0
    assert a["anti_pattern_hits"] > 0 and all(Path(p).exists() for p in a["report"].values())
    again = call("run_assessment", {"harvest_snapshot_id": mssql_harvest["snapshot_id"], "report": False})
    assert again["snapshot_id"] == a["snapshot_id"] and "report" not in again
    retired = call("classify_objects", {"harvest_snapshot_id": mssql_harvest["snapshot_id"],
                                        "dispositions": ["retire"]})
    assert retired["matched"] == a["dispositions"]["retire"] and retired["dispositions"] == {"retire": retired["matched"]}
    assert all(o["rationale"] and 0 < o["confidence"] <= 1 for o in retired["objects"])
    procs = call("classify_objects", {"harvest_snapshot_id": mssql_harvest["snapshot_id"], "names": ["*.usp_*"],
                                      "object_types": ["procedure"], "top": 3})
    assert len(procs["objects"]) == 3 and procs["truncated"] and procs["matched"] > 3
    with pytest.raises(SkillError, match="not a harvest"):
        call("classify_objects", {"harvest_snapshot_id": a["snapshot_id"]})


def test_planning_skills(call, sctx, mssql_harvest, mssql_assessment):
    asm = mssql_assessment["snapshot_id"]
    rec = call("recommend_pattern", {"assessment_snapshot_id": asm, "inputs": INPUTS})
    assert rec["pattern"] and rec["rationale"] and 0 < rec["confidence"] <= 1 and rec["snapshot_id"] == asm
    plan = call("plan_waves", {"assessment_snapshot_id": asm, "inputs": INPUTS})
    assert plan["waves"] and plan["waves"][0]["wave"] == 1 and plan["p80_hours"] >= plan["p50_hours"] > 0
    assert Path(plan["plan_path"]).exists() and sctx.store.get("wave_plan", plan_id=plan["plan_id"])
    assert sum(w["objects"] for w in plan["waves"]) + plan["decommission"] == mssql_assessment["objects"]
    w1 = call("estimate_wave", {"harvest_snapshot_id": mssql_harvest["snapshot_id"], "inputs": INPUTS, "wave": 1})
    assert w1["plan_id"] == plan["plan_id"] and w1["object_count"] == plan["waves"][0]["objects"]
    assert w1["p80_hours"] >= w1["p50_hours"] > 0 and w1["factors"]
    assert sctx.store.get("estimate", estimate_id=w1["estimate_id"])
    objs = call("estimate_wave", {"assessment_snapshot_id": asm, "inputs": INPUTS, "names": ["*.usp_*"],
                                  "record": False})
    assert objs["scope"] == "objects" and objs["object_count"] > 0 and objs["recorded"] is False
    with pytest.raises(SkillError, match="has no wave"):
        call("estimate_wave", {"assessment_snapshot_id": asm, "inputs": INPUTS, "wave": 99})


# ----------------------------------------------------------------------------- RBAC


def test_rbac_from_harvested_grants(call, sctx, teradata_harvest):
    ssid = teradata_harvest["source_system_id"]
    out = call("generate_rbac_from_legacy_grants", {"source_system_id": ssid,
                                                    "grantee_groups": {"BI_SVC": "bi_service"}})
    model = out["role_model"]
    assert out["grants"] == teradata_harvest["counts"]["grant"] == out["mapped"] + out["retired"]
    ar = {a["name"]: a for a in model["access_roles"]}
    assert ar["AR_TDPROD_EDW_RW"]["schema_wide"] and "AR_TDPROD_EDW_V_RO" in ar
    fr = {f["name"]: f for f in model["functional_roles"]}
    assert "FR_BI_SERVICE" in fr and "AR_TDPROD_EDW_RW" in fr["FR_ETL_BATCH"]["access_roles"]
    assert {u["role"] for u in model["user_assignments"]} <= set(fr)
    # Section 14.2: users receive functional roles only -- never object privileges
    user_lines = [ln for ln in out["sql"].splitlines() if " TO USER " in ln]
    assert user_lines and all(ln.startswith("GRANT ROLE FR_") for ln in user_lines)
    assert all(" TO ROLE AR_" in ln for ln in out["sql"].splitlines() if ln.startswith("GRANT SELECT"))
    assert Path(out["sql_path"]).read_text() == out["sql"]
    rows = sctx.store.query('SELECT mapped_to, mapping_status FROM "grant" WHERE source_system_id = ?', [ssid])
    assert rows and all(r["mapping_status"] in {"mapped", "retired"} for r in rows)
    assert {r["mapped_to"] for r in rows if r["mapping_status"] == "mapped"} <= set(ar)


def test_rbac_from_grant_list_retires_what_does_not_map(call):
    grants = [
        {"grantee": "jdoe", "grantee_type": "user", "privilege": "SELECT", "object": "SALES.ORDERS"},
        {"grantee": "jdoe", "grantee_type": "user", "privilege": "UPDATE", "object": "SALES.ORDERS"},
        {"grantee": "analyst_role", "grantee_type": "role", "privilege": "SELECT", "object": "SALES.CUSTOMERS"},
        {"grantee": "dba", "grantee_type": "user", "privilege": "ALTER", "object": "SALES.ORDERS"},
        {"grantee": "ops", "grantee_type": "user", "privilege": "CREATE SESSION", "object": None},
        {"grantee": "analyst_role", "grantee_type": "role", "privilege": "SELECT", "object": "OLD.ARCHIVE_2019"},
    ]
    out = call("generate_rbac_from_legacy_grants", {"grants": grants, "database": "EDW",
                                                    "retire_objects": ["OLD.*"], "persist": True})
    assert out["mapped"] == 3 and out["retired"] == 3 and out["persisted"] is False
    reasons = {m["privilege"] + ":" + str(m["object"]): m["reason"] for m in out["grant_mappings"]
               if m["status"] == "retired"}
    assert "DDL/ownership" in reasons["ALTER:SALES.ORDERS"] and "system-level" in reasons["CREATE SESSION:None"]
    assert "retire" in reasons["SELECT:OLD.ARCHIVE_2019"]
    assert all(m["mapped_to"] == "intentionally_retired" for m in out["grant_mappings"] if m["status"] == "retired")
    fr = {f["name"]: f for f in out["role_model"]["functional_roles"]}
    assert fr["FR_JDOE"]["access_roles"] == ["AR_EDW_SALES_RO", "AR_EDW_SALES_RW"]
    assert out["role_model"]["user_assignments"] == [{"user": "jdoe", "role": "FR_JDOE"}]
    with pytest.raises(SkillError, match="no database part"):
        call("generate_rbac_from_legacy_grants", {"grants": grants[:1]})


# ----------------------------------------------------------------------------- conversion


def test_convert_remediate_and_unit_tests(call, sctx):
    src = (FIXTURES / "snowconvert" / "source" / "teradata" / "upd_orders.sql").read_text()
    conv = call("convert_module", {"source_sql": src, "dialect": "teradata", "name": "upd_orders.sql",
                                   "engagement_id": "ENG-SKILLS"})
    assert conv["tool"] in {"sqlglot", "snowconvert"} and conv["issue_count"] > 0
    art = conv["artifacts"][0]
    assert Path(art["path"]).read_text() == art["converted_sql"] and art["issue_codes"]
    rem = call("remediate_ewis", {"artifact_id": art["artifact_id"]})
    pack = rem["packs"][0]
    assert rem["changes"] > 0 and Path(pack["pack_dir"], "REVIEW_CHECKLIST.md").exists()
    assert all(c["tests"] for c in pack["changes"])
    changes = sctx.store.query("SELECT change_id, decision FROM ai_change WHERE artifact_id = ?", [art["artifact_id"]])
    assert len(changes) == rem["changes"] and all(c["decision"] is None for c in changes)  # awaits human review
    tests = call("generate_unit_tests", {"run_id": conv["run_id"]})
    t = tests["artifacts"][0]
    assert t["pack_id"] == pack["pack_id"] and t["tests"] == sum(len(c["tests"]) for c in pack["changes"])
    assert t["run"]["total"] == t["tests"] and t["run"]["passed"] == t["run"]["total"]
    assert all(Path(p).exists() for p in t["test_files"])
    both = call("convert_module", {"source_sql": src, "dialect": "teradata", "remediate": True})
    assert both["remediation"][0]["changes"]
    with pytest.raises(SkillError, match="unknown artifact"):
        call("remediate_ewis", {"artifact_id": "ART-NOPE"})


# ----------------------------------------------------------------------------- ETL


def test_generate_dbt_from_mapping(call):
    files = [str(FIXTURES / "ssis" / "LoadSalesMart.dtsx"), str(FIXTURES / "informatica" / "wf_sales_dw.xml")]
    out = call("generate_dbt_from_mapping", {"files": files, "project_name": "sales_mart", "run": True,
                                             "engagement_id": "ENG-SKILLS"})
    root = Path(out["project"])
    assert (root / "dbt_project.yml").exists() and out["files"] > 0
    assert any(m.startswith("stg_") for m in out["models"]) and any(m.startswith("fct_") for m in out["models"])
    assert {j["tool"] for j in out["jobs"]} == {"ssis", "informatica"} and out["skipped"]
    assert out["run"]["ok"] and out["run"]["tests"] > 0 and out["run"]["passed"] == out["run"]["tests"]
    with pytest.raises(SkillError, match="not found"):
        call("generate_dbt_from_mapping", {"files": ["/nope/missing.dtsx"]})


# ----------------------------------------------------------------------------- validation

ORDERS_SPEC = {"object_id": "SALES.ORDERS", "source_table": "orders", "key_columns": ["order_id"],
               "partition_column": "order_date", "source_dialect": "teradata", "tier": "tier1"}


def test_generate_reconciliation_suite(call, sctx):
    out = call("generate_reconciliation_suite", {"tables": [
        ORDERS_SPEC, {**ORDERS_SPEC, "object_id": "SALES.ORDERS_T3", "tier": "tier3"}]})
    s1, s3 = out["suites"]
    assert s1["tier"] == "tier1" and s1["active_levels"][:2] == ["L0", "L1"] and "L3" in s1["active_levels"]
    assert len(s3["active_levels"]) < len(s1["active_levels"])
    assert sctx.store.get("validation_suite", suite_id=s1["suite_id"])
    docs = json.loads(Path(out["suite_path"]).read_text())
    assert [d["suite_id"] for d in docs] == [s1["suite_id"], s3["suite_id"]] and docs[0]["checks"]


def test_triage_mismatches(call, tmp_path):
    from altitude.validation.synthetic import ORDERS

    src, tgt = tmp_path / "src.duckdb", tmp_path / "tgt.duckdb"
    for path, sql in ((src, ORDERS), (tgt, ORDERS + "INSERT INTO orders SELECT * FROM orders WHERE order_id IN (5, 6, 7);")):
        con = duckdb.connect(str(path))
        con.execute(sql)
        con.close()
    out = call("triage_mismatches", {"source_path": str(src), "target_path": str(tgt), "table": ORDERS_SPEC,
                                     "as_of": "2026-10-14", "run_label": "skill-test"})
    assert out["run"]["status"] == "fail" and out["known_issues"] == ["TD-01"]
    assert out["root_cause_clusters"] == 1 and out["mismatched_rows"] == 3 and out["unmapped"] == 0
    root = next(c for c in out["clusters"] if c["root_cause"])
    assert root["signature"].startswith("duplicate_rows") and root["rationale"]
    stored = call("triage_mismatches", {"run_id": root["run_id"]})
    assert [c["cluster_id"] for c in stored["clusters"]] == [root["cluster_id"]]
    by_object = call("triage_mismatches", {"object_id": "SALES.ORDERS"})
    assert root["cluster_id"] in {c["cluster_id"] for c in by_object["clusters"]}
    with pytest.raises(SkillError):
        call("triage_mismatches", {})
