import os
import stat
import sys

import pytest

from altitude.conversion.orchestrator import ConversionOrchestrator, select_converter
from altitude.conversion.fallback import SqlglotConverter
from altitude.conversion.snowconvert import (SnowConvertCLI, SnowConvertError, locate_markers, parse_assessment_csv,
                                             parse_issues_csv)
from altitude.conversion.models import Issue

from .conftest import FAKE_SNOWCT, FIXTURES, SOURCES

REPORTS = FIXTURES / "reports"


def test_issues_report_parses_codes_severity_and_locations():
    issues = parse_issues_csv((REPORTS / "Issues.20261012.143501.csv").read_text(encoding="utf-8-sig"))
    assert len(issues) == 7  # blank trailing row skipped
    by_code = {i.code: i for i in issues}
    unrec = by_code["SSC-EWI-0001"]
    assert (unrec.category, unrec.severity, unrec.source_line, unrec.column) == ("EWI", "P1", 31, 1)
    assert unrec.file.endswith("teradata/load_customer_dim.bteq") and "\\" not in unrec.file
    # code override wins over the reported severity (Medium -> P3 anyway, but via override table)
    assert by_code["SSC-EWI-0073"].severity == "P3"
    fdm = by_code["SSC-FDM-TD0024"]
    assert fdm.category == "FDM" and fdm.severity == "P4" and "multi-line description" in fdm.message
    assert by_code["SSC-PRF-0002"].category == "PRF"
    assert by_code["SSC-EWI-TD0061"].severity == "P2"          # High
    oos = by_code["SSC-OOS-0001"]
    assert oos.category == "OOS" and oos.severity == "P2"      # empty severity -> category default
    assert oos.file == "teradata/load_customer_dim.bteq"


def test_issues_report_header_aliases_and_missing_columns():
    text = "Issue Code;Issue Severity;Message;FileName;Line Number\nSSC-EWI-0040;Low;Statement not supported;a.sql;3\n"
    (issue,) = parse_issues_csv(text)
    assert issue.code == "SSC-EWI-0040" and issue.severity == "P1" and issue.source_line == 3  # override
    with pytest.raises(SnowConvertError):
        parse_issues_csv("Severity,Line\nHigh,3\n")


def test_assessment_report():
    units = parse_assessment_csv((REPORTS / "TopLevelCodeUnits.20261012.143501.csv").read_text())
    assert [u["code_unit_id"] for u in units] == ["CU-0001", "CU-0002", "CU-0003", "CU-0004", "CU-0005"]
    pkg = units[-1]
    assert pkg["lines_of_code"] == 1204 and pkg["ewi_count"] == 14 and pkg["conversion_status"] == "Partially converted"


def test_markers_located_in_output():
    out = "SELECT 1;\n!!!RESOLVE EWI!!! /*** SSC-EWI-0073 - X ***/!!!\nSELECT 2;\n--** SSC-FDM-0007 - Y **\nSELECT 3;\n"
    a = Issue("SSC-EWI-0073", "EWI", "P3", "m", "f", source_line=2)
    b = Issue("SSC-FDM-0007", "FDM", "P4", "m", "f", source_line=3)
    c = Issue("SSC-EWI-0001", "EWI", "P1", "m", "f", source_line=9)
    locate_markers(out, [a, b, c])
    assert (a.line, b.line, c.line) == (2, 4, None)


def test_cli_discovery_version_and_invocation(tmp_path):
    cli = SnowConvertCLI(FAKE_SNOWCT)
    assert cli.available and cli.version() == "2.7.3"
    inv = cli.invocation("tsql", tmp_path / "in", tmp_path / "out")
    assert inv[len(FAKE_SNOWCT):] == ["sql-server", "-i", str(tmp_path / "in"), "-o", str(tmp_path / "out")]
    with pytest.raises(SnowConvertError):
        cli.invocation("cobol", tmp_path, tmp_path)
    # nothing on PATH and no env override -> not available -> sqlglot fallback is selected
    missing = SnowConvertCLI(env={"PATH": str(tmp_path)})
    assert not missing.available
    assert isinstance(select_converter(missing), SqlglotConverter)
    # env var override, resolved through PATH lookup of a wrapper script
    wrapper = tmp_path / "snowct"
    wrapper.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE_SNOWCT[1]} \"$@\"\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    found = SnowConvertCLI(env={"PATH": str(tmp_path) + os.pathsep + os.environ.get("PATH", "")})
    assert found.available and found.command == [str(wrapper)] and found.version() == "2.7.3"
    via_env = SnowConvertCLI(env={"ALTITUDE_SNOWCONVERT_BIN": str(wrapper), "PATH": ""})
    assert via_env.command == [str(wrapper)]


def test_cli_failure_is_reported(tmp_path):
    cli = SnowConvertCLI(FAKE_SNOWCT)
    cli.cfg = dict(cli.cfg, dialects={**cli.cfg["dialects"], "oracle": {"command": "cobol", "extensions": [".sql"]}})
    with pytest.raises(SnowConvertError, match="exited 3"):
        cli.convert(SOURCES / "oracle", "oracle", tmp_path / "out")


def test_orchestrator_with_snowconvert_cli(store, tmp_path):
    orch = ConversionOrchestrator(store, "ENG-SC", converter=SnowConvertCLI(FAKE_SNOWCT))
    run = orch.run(SOURCES / "teradata", "teradata", tmp_path / "out")
    row = store.get("conversion_run", run_id=run.run_id)
    assert row["tool"] == "snowconvert" and row["tool_version"] == "2.7.3" and row["status"] == "completed"
    issues = store.query("SELECT i.code, i.severity, i.line, d.source_line, d.category FROM conversion_issue i "
                         "JOIN conversion_issue_detail d USING (issue_id) ORDER BY d.source_line")
    assert [(i["code"], i["severity"]) for i in issues] == [
        ("SSC-FDM-TD0024", "P4"), ("SSC-EWI-0073", "P3"), ("SSC-EWI-0001", "P1")]
    assert all(i["line"] for i in issues)  # located in converted output
    assert store.scalar("SELECT count(*) FROM conversion_assessment WHERE run_id=?", [run.run_id]) == 2
