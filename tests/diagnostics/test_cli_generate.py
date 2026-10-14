"""``altitude diag ...`` commands and the stamped generator output."""

import json

from altitude.cli import main
from altitude.core.generated import is_stamped
from altitude.diagnostics import default_catalogue
from altitude.diagnostics.bootstrap import kill_test
from altitude.diagnostics.generate import generate


def test_cli_bootstrap(capsys, tmp_path):
    assert main(["diag", "bootstrap"]) == 0
    out = capsys.readouterr().out
    assert "GRANT DATABASE ROLE SNOWFLAKE.USAGE_VIEWER" in out and kill_test(out) == []
    assert main(["diag", "bootstrap", "--teardown"]) == 0
    assert "DROP ROLE IF EXISTS ALTITUDE_DIAG_ROLE" in capsys.readouterr().out
    assert main(["diag", "bootstrap", "--out", str(tmp_path), "--credit-budget", "20"]) == 0
    assert "CREDIT_QUOTA = 20" in (tmp_path / "bootstrap.sql").read_text()
    assert json.loads((tmp_path / "permission_manifest.json").read_text())["privileges"]


def test_cli_run_export_status(capsys, tmp_path, seeded_snapshot, seeded_result):
    snap, _ = seeded_snapshot
    db = str(tmp_path / "store.duckdb")
    assert main(["diag", "run", "--snapshot", str(snap.path), "--store", db, "--out", str(tmp_path / "run")]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["snapshot_id"] == snap.snapshot_id and summary["suggestions"] == len(seeded_result.suggestions)
    assert (tmp_path / "run" / "suggestions.json").exists()

    low = next(d for d in seeded_result.details if d.needs_review).id
    assert main(["diag", "status", "--store", db, "--suggestion", low, "--set-status", "accepted"]) == 1
    assert "reviewer" in capsys.readouterr().err
    assert main(["diag", "status", "--store", db, "--suggestion", low, "--set-status", "accepted",
                 "--reviewer", "lead@client"]) == 1
    assert "review queue" in capsys.readouterr().err
    assert main(["diag", "status", "--store", db, "--suggestion", low, "--review", "approved", "--reviewer", "lead@client",
                 "--set-status", "accepted"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "accepted"

    assert main(["diag", "export", "--snapshot", str(snap.path), "--store", db, "--out", str(tmp_path / "exp"),
                 "--formats", "suggestions_json", "findings_csv"]) == 0
    capsys.readouterr()
    doc = json.loads((tmp_path / "exp" / "suggestions.json").read_text())
    assert next(s for s in doc["suggestions"] if s["id"] == low)["status"] == "accepted"
    assert main(["diag", "status", "--store", db]) == 0
    assert f"{len(seeded_result.suggestions)} suggestion(s)" in capsys.readouterr().out


def test_generator_output_is_stamped_and_complete():
    files = generate()
    expected = {"diagnostics/bootstrap.sql", "diagnostics/teardown.sql", "diagnostics/permission_manifest.json",
                "diagnostics/catalogue.json"} | {f"diagnostics/detectors/{c.id}.sql" for c in default_catalogue().checks}
    assert set(files) == expected
    assert all(is_stamped(text) for text in files.values())
    assert kill_test(files["diagnostics/bootstrap.sql"]) == []
    assert generate() == files
