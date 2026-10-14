import shutil

from altitude.core.knowledge import validate_tree
from altitude.core.paths import knowledge_dir


def test_validate_runs_kpi_one_definition_check(tmp_path):
    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir(), root)
    reg = root / "semantic" / "kpi_registry.yaml"
    text = reg.read_text()
    # duplicate the first KPI under a new id: same name => conflicting definitions
    import yaml
    doc = yaml.safe_load(text)
    kpi = dict(doc["kpis"][0])
    kpi["id"] = kpi["id"] + "-DUP"
    kpi["expression"] = "SUM(1)"
    doc["kpis"].append(kpi)
    reg.write_text(yaml.safe_dump(doc, sort_keys=False))
    problems = validate_tree(root)
    assert any("KPI conflict" in p for p in problems), problems
