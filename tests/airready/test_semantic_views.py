"""M11 acceptance: semantic views are generated from the KPI registry with one definition per KPI enforced."""

import re

import pytest

from altitude.airready import cortex, harness, kpi_registry
from altitude.airready.generate import generate
from altitude.cli import main
from altitude.core.errors import KnowledgeValidationError
from altitude.core.paths import generated_dir, knowledge_dir

REG_TEXT = (knowledge_dir() / "semantic/kpi_registry.yaml").read_text()


def test_semantic_views_generated_from_registry_and_committed():
    reg = kpi_registry.load()
    out = generate()
    views = kpi_registry.semantic_views(reg)
    assert set(views) == {"sales", "finance"}
    for domain, ddl in views.items():
        rel = f"airready/semantic_views/sv_{domain}.sql"
        assert out[rel].startswith("-- AUTO-GENERATED — DO NOT EDIT")
        assert (generated_dir() / rel).read_text() == out[rel]
        dom = reg.domains[domain]
        assert ddl.startswith(f"CREATE OR REPLACE SEMANTIC VIEW {dom['semantic_view']}")
        for section in ("TABLES (", "RELATIONSHIPS (", "FACTS (", "DIMENSIONS (", "METRICS ("):
            assert section in ddl
        assert ddl.count("(") == ddl.count(")")
    # every certified KPI appears exactly once, as one metric, in exactly one view
    all_ddl = "\n".join(views.values())
    for k in reg.doc["kpis"]:
        metric = f"{k['table']}.{kpi_registry.snake(k['name'])} AS "
        assert all_ddl.count(metric) == 1, k["id"]
        assert all_ddl.count(f"[{k['id']}]") == 1


CONFLICT = """
  - id: KPI-REVENUE-GROSS-VIEW
    name: revenue
    domain: finance
    table: revenue_lines
    expression: SUM(revenue_lines.gross_amount)
    certified: true
    owner: someone@example.com
    synonyms: []
    description: A second, different definition of Revenue.
"""


def test_conflicting_kpi_definition_fails_with_precise_error():
    with pytest.raises(kpi_registry.KPIDefinitionConflict) as e:
        kpi_registry.from_text(REG_TEXT + CONFLICT)
    msg = "\n".join(e.value.problems)
    assert "'revenue' is defined twice" in msg
    assert "KPI-REVENUE-GROSS-VIEW (SUM(revenue_lines.gross_amount))" in msg
    assert "KPI-REVENUE (SUM(revenue_lines.net_amount))" in msg
    line_new = REG_TEXT.count("\n") + 3     # the conflicting entry's `name:` line
    assert re.search(rf"semantic/kpi_registry\.yaml:{line_new}: ", msg)
    assert re.search(r"at semantic/kpi_registry\.yaml:\d+; one definition per KPI", msg)


def test_synonym_collision_is_a_conflict():
    clash = REG_TEXT.replace("synonyms: [gross sales]", "synonyms: [gross sales, net revenue]")
    with pytest.raises(kpi_registry.KPIDefinitionConflict, match="'net revenue' is defined twice — KPI-GROSS-REVENUE"):
        kpi_registry.from_text(clash)


def test_punctuation_and_case_do_not_evade_the_rule():
    clash = REG_TEXT + CONFLICT.replace("name: revenue", "name: '  REVENUE!! '")
    with pytest.raises(kpi_registry.KPIDefinitionConflict):
        kpi_registry.from_text(clash)


def test_generator_refuses_to_render_conflicting_registry(tmp_path, monkeypatch):
    import shutil
    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir(), root)
    (root / "semantic/kpi_registry.yaml").write_text(REG_TEXT + CONFLICT)
    monkeypatch.setenv("ALTITUDE_HOME", str(tmp_path))
    (tmp_path / "pyproject.toml").write_text("")
    with pytest.raises(kpi_registry.KPIDefinitionConflict):
        generate()


def test_unknown_members_and_bad_expressions_are_reported():
    bad = REG_TEXT.replace("expression: SUM(revenue_lines.tax_amount)", "expression: SUM(revenue_lines.vat")
    with pytest.raises(KnowledgeValidationError) as e:
        kpi_registry.from_text(bad)
    msg = "\n".join(e.value.problems)
    assert "unknown member revenue_lines.vat" in msg and "does not parse" in msg


def test_cli_semantic_views(tmp_path, capsys):
    assert main(["airready", "semantic-views"]) == 0
    assert "CREATE OR REPLACE SEMANTIC VIEW EDW.SEMANTIC.SV_FINANCE" in capsys.readouterr().out
    p = tmp_path / "reg.yaml"
    p.write_text(REG_TEXT + CONFLICT)
    assert main(["airready", "semantic-views", "--registry", str(p)]) == 1
    assert "defined twice" in capsys.readouterr().err


def test_cortex_templates_are_consistent_and_rendered():
    templates = cortex.load_templates()
    assert cortex.validate(templates, kpi_registry.load(), harness.load_golden()) == []
    out = generate()
    assert "CREATE OR REPLACE CORTEX SEARCH SERVICE DOCS.SEARCH.CSS_POLICY_DOCS" in out[
        "airready/cortex_search/css_policy_docs.sql"]
    spec = out["airready/cortex_agents/revenue_assistant.yaml"]
    assert "cortex_analyst_text_to_sql" in spec and "EDW.SEMANTIC.SV_SALES" in spec and "ACL_GROUP" in spec
    bad = {**templates, "search_services": [{**templates["search_services"][0], "target_lag": "3 days",
                                            "acl_attribute": "OWNER"}]}
    problems = cortex.validate(bad, kpi_registry.load(), harness.load_golden())
    assert any("exceeds rubric.airready.rag_target_lag_max_hours" in p for p in problems)
    assert any("ACL attribute OWNER" in p for p in problems)
