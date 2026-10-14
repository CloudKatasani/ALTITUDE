import textwrap
from pathlib import Path

import pytest

from altitude.core.errors import KnowledgeValidationError, RubricReferenceError
from altitude.core.knowledge import validate_tree
from altitude.core.rubric import RubricSet


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(text))


def test_repository_knowledge_is_valid():
    assert validate_tree() == []


def test_rubric_resolution_and_version(tmp_path):
    _write(tmp_path, "rubrics/compute.yaml", """
        namespace: compute
        version: 1.0.0
        values:
          auto_suspend_max_seconds: 60
          nested: {a: {b: 2}}
    """)
    rs = RubricSet.load(tmp_path / "rubrics")
    assert rs.get("rubric.compute.auto_suspend_max_seconds") == 60
    assert rs.get("rubric.compute.nested.a.b") == 2
    assert rs.resolve({"x": "rubric.compute.nested.a.b", "y": 3}) == {"x": 2, "y": 3}
    with pytest.raises(RubricReferenceError):
        rs.get("rubric.compute.missing")
    v1 = rs.version
    assert v1 == RubricSet.load(tmp_path / "rubrics").version  # reproducible
    rs2 = rs.with_overrides({"compute": {"auto_suspend_max_seconds": 120}})
    assert rs2.get("rubric.compute.auto_suspend_max_seconds") == 120
    assert rs2.version != v1


def test_malformed_knowledge_fails_with_precise_error(tmp_path):
    _write(tmp_path, "rubrics/ai.yaml", """
        namespace: ai
        version: 1.0.0
        values: {review_confidence_min: 0.8}
    """)
    _write(tmp_path, "theme/default.yaml", """
        theme: default
        tokens:
          PRODUCT_NAME: X
          COMPANY_NAME: Y
          COPILOT_NAME: Z
          COLOR_PRIMARY: "#000000"
    """)
    _write(tmp_path, "rubrics/bad.yaml", """
        namespace: Bad-Name
        version: one
        values: {}
    """)
    _write(tmp_path, "unknown/thing.yaml", "a: 1\n")
    problems = validate_tree(tmp_path)
    joined = "\n".join(problems)
    assert "theme/default.yaml:3: $.tokens: 'COLOR_ACCENT' is a required property" in joined
    assert "rubrics/bad.yaml:2: $.namespace" in joined
    assert "rubrics/bad.yaml:3: $.version" in joined
    assert "unknown/thing.yaml: no schema governs this knowledge file" in joined


def test_yaml_parse_error_reports_line(tmp_path):
    _write(tmp_path, "rubrics/ai.yaml", "namespace: ai\nversion: 1.0.0\nvalues: {a: [1, 2}\n")
    with pytest.raises(KnowledgeValidationError) as e:
        RubricSet.load(tmp_path / "rubrics")
    problems = validate_tree(tmp_path)
    assert any("ai.yaml:3: YAML parse error" in p for p in problems) or e.value.problems
