import json

from altitude.cli import main

from .conftest import FIXTURES, SOURCES


def _json(capsys):
    return json.loads(capsys.readouterr().out)


def test_cli_end_to_end(tmp_path, capsys):
    db = str(tmp_path / "alt.duckdb")
    assert main(["conversion", "run", str(SOURCES / "teradata"), "--dialect", "teradata", "--out",
                 str(tmp_path / "out"), "--db", db, "--remediate"]) == 0
    run = _json(capsys)
    assert run["tool"] == "sqlglot" and len(run["artifacts"]) == 2 and set(run["pr_packs"]) == set(run["artifacts"])

    assert main(["conversion", "status", "--db", db]) == 0
    status = {r["target_path"]: r for r in _json(capsys)}
    art = status["upd_orders.sql"]["artifact_id"]
    assert status["upd_orders.sql"]["factory_state"] == "AI-remediated"

    assert main(["conversion", "promote", art, "--by", "rm", "--db", db]) == 1
    assert "not promotable" in capsys.readouterr().err

    packs = {p.parent.name: json.loads(p.read_text()) for p in (tmp_path / "out").rglob("PRP-*/manifest.json")}
    manifest = next(m for m in packs.values() if m["artifact_id"] == art)
    for change_id in manifest["changes"]:
        assert main(["conversion", "review", "--change", change_id, "--reviewer", "lead", "--decision",
                     "approved", "--db", db]) == 0
    assert main(["conversion", "review-artifact", art, "--reviewer", "peer", "--decision", "approved", "--db", db]) == 0
    capsys.readouterr()
    assert main(["conversion", "test", art, "--db", db]) == 0
    assert _json(capsys)["pass_rate"] == 1.0
    assert main(["conversion", "gate", art, "--db", db]) == 0
    assert _json(capsys)["passed"] is True
    assert main(["conversion", "promote", art, "--by", "rm", "--db", db]) == 0
    assert _json(capsys)["promoted_by"] == "rm"


def test_cli_parse_report_and_tool(capsys):
    assert main(["conversion", "parse-report", str(FIXTURES / "reports" / "Issues.20261012.143501.csv")]) == 0
    assert len(_json(capsys)) == 7
    assert main(["conversion", "parse-report", "--assessment",
                 str(FIXTURES / "reports" / "TopLevelCodeUnits.20261012.143501.csv")]) == 0
    assert _json(capsys)[0]["code_unit_id"] == "CU-0001"
    assert main(["conversion", "tool", "--snowconvert", "/nonexistent/snowct"]) == 0
    assert _json(capsys)["converter"] == "sqlglot"
