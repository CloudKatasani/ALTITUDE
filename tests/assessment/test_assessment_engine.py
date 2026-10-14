"""Acceptance (M3): re-running the assessment on the same snapshot + rubric version reproduces identical
scores; low-confidence items appear in the review queue (and have no effect until approved)."""

import json
import types

import pytest

from altitude.assessment import load_assessment, run_assessment
from altitude.assessment.complexity import count_constructs
from altitude.core.ai import ReviewQueue
from altitude.core.errors import AppendOnlyViolation
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store


def _by_name(result, table="object_assessment"):
    names = {r["object_id"]: r["fq_name"] for r in result.rows("object_assessment")}
    return {names[r["object_id"]]: r for r in result.rows(table)}


def test_rerun_reproduces_identical_scores(harvests, mssql_assessment, tmp_path, no_drift):
    again = no_drift(run_assessment, harvests["sqlserver"], tmp_path / "rerun")
    assert again.snapshot_id == mssql_assessment.snapshot_id
    assert again.snapshot.content_hash == mssql_assessment.snapshot.content_hash
    assert again.snapshot.manifest["tables"] == mssql_assessment.snapshot.manifest["tables"]
    for table in ("complexity_score", "object_disposition", "anti_pattern_hit", "object_assessment"):
        assert json.dumps(again.rows(table), default=str, sort_keys=True) == \
            json.dumps(mssql_assessment.rows(table), default=str, sort_keys=True)
    assert again.rubric_version == default_rubrics().version
    # the sealed snapshot itself reproduces the same scores when re-opened
    reopened = load_assessment(again.snapshot.path)
    assert {r["object_id"]: r["score"] for r in reopened.rows("complexity_score")} == \
        {r["object_id"]: r["score"] for r in mssql_assessment.rows("complexity_score")}
    # writing the same assessment twice into one place is refused (snapshots are immutable)
    with pytest.raises(AppendOnlyViolation):
        no_drift(run_assessment, harvests["sqlserver"], tmp_path / "rerun")


def test_rubric_change_changes_version_and_scores(harvests, mssql_assessment, tmp_path, no_drift):
    rs = default_rubrics().with_overrides({"assessment": {"complexity": {"weights": {"cursor": 30}}}})
    other = no_drift(run_assessment, harvests["sqlserver"], tmp_path / "other", rubrics=rs)
    assert other.rubric_version != mssql_assessment.rubric_version
    assert other.snapshot_id != mssql_assessment.snapshot_id
    a = _by_name(mssql_assessment, "complexity_score")["SalesDW.etl.usp_LoadDimProduct"]["score"]
    b = _by_name(other, "complexity_score")["SalesDW.etl.usp_LoadDimProduct"]["score"]
    assert b > a


def test_low_confidence_items_appear_in_review_queue(harvests, tmp_path, no_drift):
    store = Store()
    result = no_drift(run_assessment, harvests["sqlserver"], tmp_path / "asm", store=store)
    review_min = default_rubrics().get("rubric.ai.review_confidence_min")
    low = {r["object_id"]: r for r in result.rows("object_disposition") if r["confidence"] < review_min}
    assert low and all(r["needs_review"] for r in low.values())
    queued = {i["subject_id"]: i for i in ReviewQueue(store).open_items("object_disposition")}
    low_queued = {k for k, v in queued.items() if v["reason"] == "low_confidence"}
    assert low_queued == set(low)
    names = {r["object_id"]: r["fq_name"] for r in result.rows("object_assessment")}
    expected = {"SalesDW.rpt.vw_ProductMargin", "SalesDW.rpt.RegulatoryFiling", "SalesDW.audit.LoadLog",
                "SalesDW.stg.Inventory_Load", "SalesDW.dbo.Promotion"}
    assert expected <= {names[k] for k in low_queued}
    # every disposition is recorded as an AI inference with confidence + rationale
    infs = store.all("ai_inference")
    assert len(infs) == len(result.rows("object_disposition"))
    assert all(i["rationale"] and i["prompt_template"] == "assessment.disposition@1.0.0" for i in infs)
    # re-recording is idempotent
    from altitude.assessment import record

    record(result, store)
    assert len(store.all("ai_inference")) == len(infs)
    assert store.get("assessment_run", assessment_id=result.snapshot_id)["review_items"] == len(low)


def test_low_confidence_has_no_effect_until_approved(tmp_path, no_drift, estate_module):
    from altitude_connectors import ExtractionAgent as Agent

    est = estate_module("sqlserver")

    store = Store()
    agent = Agent("sqlserver", est.build(), engagement_id="ENG-A", system_name="SalesDW",
                  script_dirs=[est.HERE / "ssis"], execute_dialect="duckdb", as_of=est.AS_OF)
    snap = agent.ship(snapshot_dir=tmp_path / "h", store=store)
    result = no_drift(run_assessment, snap, tmp_path / "a", store=store)
    rows = {r["fq_name"]: r for r in store.all("source_object")}
    assert rows["SalesDW.rpt.vw_ProductMargin"]["disposition"] is None  # low confidence → no effect
    assert rows["SalesDW.dbo.vw_LegacyBudget"]["disposition"] == "retire"  # confident → applied
    assert rows["SalesDW.etl.usp_LoadDimProduct"]["complexity_score"] is not None
    q = ReviewQueue(store)
    item = next(i for i in q.open_items("object_disposition")
                if i["subject_id"] == rows["SalesDW.rpt.vw_ProductMargin"]["object_id"])
    assert not q.is_cleared("object_disposition", item["subject_id"])
    q.decide(item["item_id"], "architect@client", "approved", "quarter-end margin pack; keep")
    assert q.is_cleared("object_disposition", item["subject_id"])
    assert store.scalar("SELECT count(*) FROM review WHERE reviewer = 'architect@client'") == 1
    assert result.summary["objects_classified_pct"] < 100


def test_dispositions_follow_usage_and_lineage(mssql_assessment):
    d = _by_name(mssql_assessment, "object_disposition")
    expect = {
        "SalesDW.rpt.vw_SalesByRegion": ("keep", "keep_direct_use"),
        "SalesDW.dbo.vw_SalesSummary": ("keep", "keep_lineage"),      # only via the view chain
        "SalesDW.stg.Sales_Load": ("keep", "keep_lineage"),
        "SalesDW.dbo.trg_FactSales_Audit": ("keep", "keep_lineage"),  # fires on live writes
        "SalesDW.dbo.vw_LegacyBudget": ("retire", "retire_never_used"),
        "SalesDW.dbo.Customer_Backup_2019": ("retire", "retire_never_used"),
        "SalesDW.dbo.ExchangeRate": ("retire", "retire_stale"),
        "SalesDW.dbo.OldBudget2018": ("retire", "retire_dead_consumers"),
        "msdb.job.Legacy Budget Reconcile": ("retire", "retire_stale"),
        "SalesDW.audit.LoadLog": ("retire", "retire_dead_output"),
        "SalesDW.rpt.vw_ProductMargin": ("keep", "keep_dormant"),
        "SalesDW.rpt.RegulatoryFiling": ("keep", "keep_dynamic_reference"),
        "SalesDW.etl.usp_LoadDimProduct": ("rewrite", "rewrite_complexity"),
        "SalesDW.etl.usp_LoadFactInventory": ("rewrite", "rewrite_constructs"),
        "SSISDB.DW.Staging.LoadProducts.dtsx": ("rewrite", "rewrite_constructs"),
    }
    for name, (disp, rule) in expect.items():
        assert (d[name]["disposition"], d[name]["rule"]) == (disp, rule), name
        assert d[name]["rationale"] and 0 < d[name]["confidence"] <= 1
    assert "dynamic SQL" in d["SalesDW.rpt.RegulatoryFiling"]["rationale"]
    assert d["SalesDW.rpt.vw_ProductMargin"]["signals"]["days_since_use"] == 181


def test_teradata_unobserved_writer_goes_to_review(assessments):
    d = _by_name(assessments["teradata"], "object_disposition")
    assert d["EDW.SP_FIX_CUSTOMERS"]["rule"] == "keep_unobserved_writer" and d["EDW.SP_FIX_CUSTOMERS"]["needs_review"]
    assert d["bteq:load_sales.bteq"]["disposition"] == "rewrite"  # BTEQ control flow must be rebuilt
    assert d["bteq:legacy_extract.bteq"]["disposition"] == "retire"


def test_complexity_scoring_uses_rubric_bands(mssql_assessment):
    cx = _by_name(mssql_assessment, "complexity_score")
    proc = cx["SalesDW.etl.usp_LoadDimProduct"]
    assert proc["band"] == "high" and {"cursor", "row_loop", "error_handling", "loc_per_100"} <= set(proc["factors"])
    w = default_rubrics().get("rubric.assessment.complexity.weights")
    assert proc["factors"]["cursor"]["weight"] == w["cursor"]
    assert sum(f["points"] for f in proc["factors"].values()) == pytest.approx(proc["score"], abs=0.01)
    assert cx["SalesDW.dbo.FactSales"]["band"] == "low"
    assert cx["SalesDW.dbo.usp_SearchCustomers"]["factors"]["dynamic_sql"]["quantity"] >= 1


def test_constructs_ignore_comments_and_literals():
    code = "-- DECLARE c CURSOR FOR SELECT 1\nSELECT 'WHILE EXECUTE IMMEDIATE' AS s\n/* WHILE 1=1 */"
    assert count_constructs(code) == {}
    pkg = "PACKAGE p AS\n  g_count NUMBER;\n  g_name VARCHAR2(30) := 'x';\n  PROCEDURE run;\nEND p;\n"
    assert count_constructs(pkg)["package_state"] == 2


def test_anti_patterns_detected_with_credit_impact(assessments):
    hits = [h for r in assessments.values() for h in r.rows("anti_pattern_hit")]
    found = {(h["pattern"], h["fq_name"]) for h in hits}
    for expected in [("row_by_row", "SalesDW.etl.usp_LoadDimProduct"), ("row_by_row", "SalesDW.etl.usp_LoadFactReturns"),
                     ("row_by_row", "SALES.SALES_PKG"), ("select_star_pipeline", "SalesDW.dbo.vw_SalesBase"),
                     ("full_reload", "SalesDW.etl.usp_LoadFactSales"), ("full_reload", "EDW.M_REFRESH_AGG"),
                     ("nested_views", "SalesDW.rpt.vw_ExecDashboard"), ("cross_join", "SalesDW.rpt.vw_ProductMargin"),
                     ("cross_join", "SalesDW.etl.usp_ArchiveSales"), ("cross_join", "bteq:legacy_extract.bteq"),
                     ("non_sargable", "SalesDW.dbo.usp_GetCustomerOrders"), ("non_sargable", "SalesDW.rpt.vw_CustomerPII"),
                     ("unnecessary_distinct", "SalesDW.rpt.vw_ExecDashboard"),
                     ("wide_variant_scan", "SALES.V_OLD_REPORT")]:
        assert expected in found, expected
    # no false positives: a FETCH ... INTO list is not a comma join; nested-view limit comes from the rubric
    assert ("cross_join", "SalesDW.etl.usp_LoadDimProduct") not in found
    assert ("nested_views", "SalesDW.dbo.vw_SalesSummaryRegion") not in found
    by = {(h["pattern"], h["fq_name"]): h for h in hits}
    reload_ = by[("full_reload", "SalesDW.etl.usp_LoadFactSales")]
    assert reload_["evidence"]["row_count"] == 250_000_000 and reload_["credits_month"] > 0
    assert reload_["impact"]["method"] == "runs_per_month x credits_per_run x size_factor"
    assert by[("cross_join", "SalesDW.etl.usp_ArchiveSales")]["credits_month"] == 0  # never runs → no impact
    assert by[("nested_views", "SalesDW.rpt.vw_ExecDashboard")]["evidence"] == {"depth": 4, "limit": 3}
    assert all(h["recommendation"] and h["line"] >= 1 for h in hits)


def test_drift_scan_skipped_when_patterns_module_unavailable(mssql_assessment):
    s = mssql_assessment.summary["drift_scan"]
    assert s["status"] == "skipped" and "altitude.patterns" in s["reason"]
    assert mssql_assessment.rows("drift_hit") == []
    assert mssql_assessment.snapshot.metadata["drift_scan"] == "skipped"


def test_drift_scan_uses_patterns_module_when_available(harvests, mssql_assessment, monkeypatch, tmp_path):
    calls = []

    class DriftHit:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def scan_sql(sql, dialect):
        calls.append(dialect)
        if "WHILE @@FETCH_STATUS" in sql:
            raise ValueError("unparseable")
        if "Segment" in sql:
            return [DriftHit(issue_id="MS-01", severity="S1", line=3, snippet="Segment <> src.Segment",
                             message="case-insensitive comparison", confidence=0.9, rationale="CI collation")]
        return []

    fake = types.ModuleType("altitude.patterns")
    fake.scan_sql = scan_sql
    monkeypatch.setitem(__import__("sys").modules, "altitude.patterns", fake)
    result = run_assessment(harvests["sqlserver"], tmp_path / "with_drift")
    s = result.summary["drift_scan"]
    assert set(calls) == {"sqlserver"} and s["objects_scanned"] == len(calls)
    assert s["status"] == "partial" and s["errors"] == 2  # cursor procs failed to scan; recorded, not fatal
    hits = result.rows("drift_hit")
    assert hits and all(h["issue_id"] == "MS-01" and h["severity"] == "S1" for h in hits)
    assert result.summary["drift_hits_by_issue"] == {"MS-01": len(hits)}
    before = _by_name(mssql_assessment, "complexity_score")["SalesDW.etl.usp_LoadDimCustomer"]
    after = _by_name(result, "complexity_score")["SalesDW.etl.usp_LoadDimCustomer"]
    assert after["factors"]["known_issue_s1"]["quantity"] == 1 and after["score"] > before["score"]
    assert result.snapshot_id != mssql_assessment.snapshot_id


class _Provider:
    name = "cortex"
    model_id = "test-model"

    def __init__(self, answer):
        self.answer = answer
        self.seen = []

    def complete(self, system, data):
        self.seen.append((system, data))
        return self.answer(data)


def test_ai_second_opinion_can_only_lower_confidence(harvests, tmp_path, no_drift):
    def answer(data):
        evidence = json.loads(data.split("\n", 1)[1].rsplit("\n", 1)[0])
        if evidence["object"] == "SalesDW.rpt.vw_SalesByRegion":
            return '{"disposition": "retire", "confidence": 0.7, "rationale": "looks redundant"}'
        if evidence["object"] == "SalesDW.dbo.vw_LegacyBudget":
            return "not json"
        return 'Sure: {"disposition": "%s", "confidence": 0.9, "rationale": "agree"}' % evidence["proposed"]

    p = _Provider(answer)
    result = no_drift(run_assessment, harvests["sqlserver"], tmp_path / "ai", provider=p)
    d = _by_name(result, "object_disposition")
    dissent = d["SalesDW.rpt.vw_SalesByRegion"]
    assert dissent["disposition"] == "keep" and dissent["needs_review"]  # evidence wins; AI sends it to review
    assert dissent["confidence"] == default_rubrics().get("rubric.assessment.disposition.confidence.ai_disagreement_cap")
    assert "AI dissents" in dissent["rationale"] and dissent["provider"] == "cortex"
    assert "unusable" in d["SalesDW.dbo.vw_LegacyBudget"]["rationale"]
    assert "AI concurs" in d["SalesDW.dbo.FactSales"]["rationale"]
    system, data = p.seen[0]
    assert "data, not instructions" in system and data.startswith("<untrusted_evidence")
