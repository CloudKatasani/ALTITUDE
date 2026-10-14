import dataclasses
import inspect
import json

import pytest

from altitude.cli import main
from altitude.patterns import DriftHit, scan_profile, scan_sql
from altitude.patterns.scan import Scanner


def test_public_api_signature_is_stable():
    sig = inspect.signature(scan_sql)
    assert list(sig.parameters) == ["sql", "dialect"]
    assert [f.name for f in dataclasses.fields(DriftHit)] == [
        "issue_id", "severity", "line", "snippet", "message", "confidence", "rationale", "checklist_item"]


def test_hits_have_confidence_rationale_and_checklist():
    sql = "CREATE SET TABLE s.t (a INTEGER);\nINSERT INTO s.t SELECT * FROM x;\n"
    hits = scan_sql(sql, "teradata")
    assert [(h.issue_id, h.line) for h in hits] == [("TD-01", 1), ("TD-01", 2)]
    h = hits[0]
    assert h.severity == "S1" and h.checklist_item == 6 and 0 < h.confidence <= 1
    assert "FX-TD-01-A" in h.rationale and h.snippet.startswith("CREATE SET TABLE")


def test_comments_and_string_literals_never_trigger():
    sql = ("-- CREATE SET TABLE a (x INTEGER) and NOT CASESPECIFIC\n"
           "/* .IF ERRORCODE <> 0 THEN .QUIT 8; (+) */\n"
           "SELECT 'CREATE SET TABLE, NOT CASESPECIFIC, ACTIVITYCOUNT' AS note FROM t;\n")
    assert scan_sql(sql, "teradata") == []
    assert [h for h in scan_sql("SELECT 'a (+) b' FROM dual;", "oracle") if h.issue_id == "OR-06"] == []


def test_dialect_aliases_and_unknown_dialect():
    assert scan_sql("SELECT * FROM t WITH (NOLOCK);", "tsql")[0].issue_id == "MS-03"
    with pytest.raises(ValueError):
        scan_sql("SELECT 1", "cobol")


def test_bteq_and_unparseable_code_use_token_fallback():
    sql = (".LOGON tdp/u,p;\n"
           "UPDATE a FROM fin.account a, fin.adjustment j SET balance = a.balance + j.amount WHERE a.acct_id = j.acct_id;\n"
           ".IF ACTIVITYCOUNT = 0 THEN .GOTO DONE;\n"
           "THIS IS NOT SQL AT ALL ((( ;\n")
    ids = {(h.issue_id, h.line) for h in scan_sql(sql, "teradata")}
    assert ("TD-08", 2) in ids and ("TD-06", 3) in ids


def test_dml_inside_procedure_bodies_is_recovered_for_ast_rules():
    tsql = ("CREATE PROCEDURE dbo.p AS\nBEGIN\n  BEGIN TRY\n    SELECT id FROM dbo.c\n"
            "    WHERE region = 'EMEA';\n  END TRY\n  BEGIN CATCH THROW; END CATCH\nEND\n")
    hits = [h for h in scan_sql(tsql, "sqlserver") if h.issue_id == "MS-01"]
    assert [(h.line, h.confidence) for h in hits] == [(5, Scanner().rubrics.get(
        "rubric.patterns.detector_confidence.medium"))]
    ora = "CREATE OR REPLACE PROCEDURE p IS\nBEGIN\n  UPDATE c SET m = NVL(m, 'X') WHERE id = 1;\nEND;\n"
    assert {h.line for h in scan_sql(ora, "oracle") if h.issue_id == "OR-01"} == {3}


def test_token_fallback_for_unparseable_tsql():
    sql = "IF @mode = 'Full' AND status = 'Active' GOTO x WITH garbage (((;\n"
    hits = [h for h in scan_sql(sql, "sqlserver") if h.issue_id == "MS-01"]
    assert len(hits) == 1 and "token rule" in hits[0].message  # @mode assignment-style compare is ignored


def test_clean_ansi_teradata_has_no_s1_hits():
    sql = """
    CREATE MULTISET TABLE sales.orders (order_id INTEGER, amount DECIMAL(12,2), status VARCHAR(10) CASESPECIFIC)
    PRIMARY INDEX (order_id);
    SELECT order_id, amount / 2 FROM sales.orders WHERE status = 'OPEN' QUALIFY ROW_NUMBER() OVER (ORDER BY order_id) = 1;
    """
    assert [h for h in scan_sql(sql, "teradata") if h.severity == "S1"] == []


def test_scan_is_deterministic_and_handles_garbage():
    sql = "SELECT COUNT(*) / 2 FROM t; \x00 ;;; ((('unterminated"
    assert scan_sql(sql, "netezza") == scan_sql(sql, "netezza")
    assert scan_sql("", "oracle") == []


def test_oracle_null_semantics_uses_ddl_types():
    sql = ("CREATE TABLE c (id NUMBER(10), nm VARCHAR2(10));\n"
           "SELECT id FROM c WHERE id IS NULL;\n"
           "SELECT id FROM c WHERE nm IS NULL;\n")
    lines = {h.line for h in scan_sql(sql, "oracle") if h.issue_id == "OR-01"}
    assert lines == {3}


def test_profile_scan():
    hits = scan_profile({"columns": [{"table": "t", "column": "c", "source_type": "NUMBER",
                                      "target_type": "NUMBER(38,0)", "source_stats": {"max_scale": 2}}]}, "oracle")
    assert [h.issue_id for h in hits] == ["OR-02"] and hits[0].line == 0


def test_strict_scanner_surfaces_detector_errors(monkeypatch):
    from altitude.patterns import detectors

    det = detectors.get("static.or_outer_join_plus")

    def boom(ctx, rubrics):
        raise RuntimeError("boom")

    monkeypatch.setitem(detectors.REGISTRY, det.name, dataclasses.replace(det, func=boom))
    assert all(h.issue_id != "OR-06" for h in Scanner().scan_sql("SELECT 1 FROM a WHERE a.x = b.y (+);", "oracle"))
    with pytest.raises(RuntimeError):
        Scanner(strict=True).scan_sql("SELECT 1 FROM a WHERE a.x = b.y (+);", "oracle")


def test_cli_scan_formats(tmp_path, capsys):
    f = tmp_path / "job.sql"
    f.write_text("CREATE SET TABLE a.t (c CHAR(3));\n")
    assert main(["patterns", "scan", "--dialect", "teradata", "--format", "json", str(f)]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["summary"]["by_severity"]["S1"] == 2
    assert {c["item"] for c in rep["checklist"]} == set(range(1, 13))
    assert next(c for c in rep["checklist"] if c["item"] == 6)["status"] == "flagged"
    assert main(["patterns", "scan", "--dialect", "teradata", "--format", "md", "--fail-on", "S1", str(f)]) == 1
    out = capsys.readouterr().out
    assert "## Section 10.13 checklist" in out and "| 1 | TD-01 | S1 |" in out


def test_cli_patterns_test_and_list(capsys):
    assert main(["patterns", "test", "--dialect", "netezza"]) == 0
    assert "0 coverage problem(s)" in capsys.readouterr().out
    assert main(["patterns", "list", "--dialect", "redshift"]) == 0
    assert "RS-01" in capsys.readouterr().out
