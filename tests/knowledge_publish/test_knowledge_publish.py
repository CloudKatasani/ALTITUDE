import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
import sqlglot

from altitude.cli import main
from altitude.core.errors import KnowledgeValidationError
from altitude.core.generated import is_stamped
from altitude.core.paths import knowledge_dir
from altitude.core.store import Store
from altitude.knowledge_publish import publish, record_observation
from altitude.knowledge_publish.generate import generate
from altitude.patterns.library import default_library

NOW = datetime(2026, 10, 14, 12)


def test_publish_loads_canonical_tables_idempotently():
    store = Store()
    lib = default_library()
    res = publish(store, now=NOW)
    assert res.known_issues == len(lib.issues) and res.test_cases == len(lib.tests)
    assert store.scalar("SELECT count(*) FROM known_issue") == len(lib.issues)
    assert store.scalar("SELECT count(*) FROM pattern") == len(lib.mappings)
    assert store.scalar("SELECT count(*) FROM fix_pattern") == sum(len(i.fix_patterns) for i in lib.issues.values())
    row = store.get("known_issue", issue_id="OR-01")
    assert row["detection_rule"] == "static.or_empty_string_null" and row["fix_pattern_id"] == "FX-OR-01-A"
    assert "TC-OR-01-001" in row["test_case_ids"]
    tc = store.get("test_case", test_case_id="TC-TD-01-001")
    definition = json.loads(tc["definition"]) if isinstance(tc["definition"], str) else tc["definition"]
    assert definition["kind"] == "golden" and definition["expected_rows"] == [[3, 175.5]]
    assert store.get("rubric", namespace="validation")["current_version"] == "1.0.0"
    assert store.get("rubric_version", namespace="patterns", version="1.0.0") is not None

    assert record_observation(store, "OR-01", 3) == 3
    res2 = publish(store, now=NOW)
    assert res2.rubric_versions_added == 0
    assert store.scalar("SELECT count(*) FROM known_issue") == len(lib.issues)
    assert store.get("known_issue", issue_id="OR-01")["frequency_observed"] == 3  # survives republish


def _copy_knowledge(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir(), root)
    return root


def test_changed_rubric_requires_version_bump(tmp_path):
    root = _copy_knowledge(tmp_path)
    store = Store()
    publish(store, root=root, now=NOW)
    p = root / "rubrics" / "validation.yaml"
    p.write_text(p.read_text().replace("review_by_max_days: 180", "review_by_max_days: 365"))
    with pytest.raises(KnowledgeValidationError, match="bump the version"):
        publish(store, root=root, now=NOW)
    p.write_text(p.read_text().replace("version: 1.0.0", "version: 1.1.0", 1))
    assert publish(store, root=root, now=NOW).rubric_versions_added == 1
    assert store.get("rubric", namespace="validation")["current_version"] == "1.1.0"


def test_invalid_knowledge_is_not_published(tmp_path):
    root = _copy_knowledge(tmp_path)
    p = root / "dialects" / "oracle" / "known_issues.yaml"
    p.write_text(p.read_text().replace("severity: S1", "severity: S9", 1))
    with pytest.raises(KnowledgeValidationError):
        publish(Store(), root=root)


def test_generated_renderings_are_stamped_deterministic_and_valid():
    out = generate()
    assert set(out) == {"knowledge_publish/known_issues.md", "knowledge_publish/mappings.md",
                        "knowledge_publish/drift_checklist.md", "knowledge_publish/pattern_library.sql"}
    assert out == generate()
    assert all(is_stamped(c) for c in out.values())
    sql = out["knowledge_publish/pattern_library.sql"]
    statements = [s for s in sqlglot.parse(sql, read="snowflake") if s is not None]
    lib = default_library()
    inserts = [s for s in statements if s.key == "insert"]
    assert len(inserts) == (len(lib.mappings) + len(lib.issues) + len(lib.tests) +
                            sum(len(i.fix_patterns) for i in lib.issues.values()) + 2)
    md = out["knowledge_publish/known_issues.md"]
    for iid in ("TD-01", "OR-11", "MS-10", "NZ-04", "RS-05", "XD-07"):
        assert f"### {iid} " in md
    checklist = out["knowledge_publish/drift_checklist.md"]
    assert "| 2 | NULL vs empty string | — | OR-01 |" in checklist


def test_cli(tmp_path, capsys):
    db = tmp_path / "kb.duckdb"
    assert main(["knowledge-publish", "load", "--db", str(db)]) == 0
    assert json.loads(capsys.readouterr().out)["known_issues"] == len(default_library().issues)
    assert main(["knowledge-publish", "render", "--out", str(tmp_path / "r")]) == 0
    assert (tmp_path / "r" / "knowledge_publish" / "known_issues.md").exists()
    capsys.readouterr()
    assert main(["knowledge-publish", "stats"]) == 0
    assert json.loads(capsys.readouterr().out)["coverage_problems"] == []
