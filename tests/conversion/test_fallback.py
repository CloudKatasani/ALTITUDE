import sqlglot

from altitude.conversion.fallback import SqlglotConverter
from altitude.conversion.splitter import split_statements

from .conftest import SOURCES


def _codes(cf):
    return [i.code for i in cf.issues]


def test_splitter_handles_bteq_plsql_and_go_batches():
    td = ".LOGON a/b,c;\nINSERT INTO t SELECT 1;\nREPLACE PROCEDURE p()\nBEGIN\n  IF x = 1 THEN SET y = 2; END IF;\nEND;\n.LOGOFF\n"
    kinds = [(u.kind, u.start_line, u.end_line) for u in split_statements(td, "teradata")]
    assert kinds == [("dot", 1, 1), ("sql", 2, 2), ("sql", 3, 6), ("dot", 7, 7)]
    ora = "CREATE PACKAGE BODY p AS\n PROCEDURE a IS BEGIN NULL; END a;\nEND p;\n/\nSELECT ';' FROM dual;\n"
    assert [(u.start_line, u.end_line) for u in split_statements(ora, "oracle")] == [(1, 3), (5, 5)]
    ts = "CREATE PROC p AS\nBEGIN\n SELECT 1;\n SELECT 2;\nEND\nGO\nSELECT [a;b] FROM t;\n"
    assert [(u.start_line, u.end_line) for u in split_statements(ts, "tsql")] == [(1, 5), (7, 7)]


def test_teradata_bteq_constructs_become_issues():
    conv = SqlglotConverter()
    cf = conv.convert_text((SOURCES / "teradata" / "load_customer_dim.bteq").read_text(), "teradata", "x.bteq")
    codes = _codes(cf)
    assert codes.count("ALT-EWI-TD0001") == 5      # .LOGON, 2x .SET, .LOGOFF, .QUIT
    assert codes.count("ALT-EWI-TD0002") == 4      # 3x .IF ERRORCODE, .LABEL
    assert {"ALT-FDM-TD0005", "ALT-FDM-TD0007", "ALT-EWI-TD0006", "ALT-EWI-TD0008"} <= set(codes)
    known = {i.code: i.known_issue for i in cf.issues}
    assert known["ALT-FDM-TD0005"] == "TD-01" and known["ALT-EWI-TD0001"] == "TD-06"
    # dot-commands are commented out, real SQL is transpiled (SEL -> SELECT, TOP -> LIMIT)
    assert "-- .LOGON" in cf.output_text and "\n.LOGON" not in cf.output_text
    assert "LIMIT 10" in cf.output_text and "SEL customer_id" not in cf.output_text
    lines = cf.output_text.splitlines()
    for issue in cf.issues:
        assert issue.code in lines[issue.line - 1] and "!!!RESOLVE EWI!!!" in lines[issue.line - 1]
        assert issue.source_line and issue.region_end >= issue.line


def test_tsql_and_oracle_constructs():
    conv = SqlglotConverter()
    ts = conv.convert_text((SOURCES / "tsql" / "usp_purge_stage.sql").read_text(), "tsql")
    assert {"ALT-EWI-MS0001", "ALT-EWI-MS0007", "ALT-EWI-MS0004", "ALT-EWI-MS0003", "ALT-FDM-MS0005",
            "ALT-FDM-MS0008"} == set(_codes(ts))
    sev = {i.code: i.severity for i in ts.issues}
    assert sev["ALT-EWI-MS0001"] == "P1" and sev["ALT-EWI-MS0004"] == "P1" and sev["ALT-EWI-MS0003"] == "P2"
    code = "\n".join(ln for ln in ts.output_text.splitlines() if not ln.startswith("--"))
    assert "COALESCE(o.discount, 0)" in code and "NOLOCK" not in code
    ora = conv.convert_text((SOURCES / "oracle" / "sales_pkg.sql").read_text(), "oracle")
    assert {"ALT-EWI-OR0001", "ALT-EWI-OR0002", "ALT-EWI-OR0003", "ALT-EWI-OR0004", "ALT-EWI-OR0005",
            "ALT-EWI-OR0006", "ALT-FDM-OR0007"} == set(_codes(ora))


def test_parse_errors_and_clean_sql():
    conv = SqlglotConverter()
    clean = conv.convert_text("SELECT TOP 3 a FROM t;\n", "tsql")
    assert clean.issues == [] and "LIMIT 3" in clean.output_text
    assert sqlglot.parse_one(clean.output_text, read="snowflake")
    broken = conv.convert_text("SELECT FROM WHERE ((;\n", "oracle")
    assert [i.code for i in broken.issues] == ["ALT-EWI-0003"] and broken.issues[0].severity == "P1"
    assert "-- SELECT FROM WHERE" in broken.output_text
    unknown = conv.convert_text(".FOO bar\n", "teradata")
    assert [i.code for i in unknown.issues] == ["ALT-EWI-0003"]


def test_conversion_is_deterministic():
    conv = SqlglotConverter()
    a = conv.convert(SOURCES / "teradata", "teradata")
    b = conv.convert(SOURCES / "teradata", "teradata")
    assert [f.output_text for f in a.files] == [f.output_text for f in b.files]
    assert [[i.to_dict() for i in f.issues] for f in a.files] == [[i.to_dict() for i in f.issues] for f in b.files]
