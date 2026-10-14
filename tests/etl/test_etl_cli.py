import json

from altitude.cli import main
from altitude.core.generated import is_stamped
from altitude.core.store import Store
from altitude.etl import generate as etl_generate
from altitude.etl.harness import DbtHarness

from .conftest import CONTROLM, DTSX, POWERCENTER, SQLAGENT


def test_cli_dbt_run_and_assess(tmp_path, capsys):
    db = str(tmp_path / "alt.duckdb")
    out = tmp_path / "dbt"
    assert main(["etl", "dbt", str(POWERCENTER), str(DTSX), "--out", str(out), "--run", "--db", db]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["run"]["errors"] == {} and summary["run"]["failed"] == [] and summary["run"]["tests"] > 40
    assert (out / "dbt_project.yml").exists() and (out / "models/marts/fct_sales.sql").exists()
    # the written project is a self-contained dbt project the harness can re-read from disk
    compiled, order, _ = DbtHarness(project_dir=out).compile()
    assert order.index("dim_product") < order.index("fct_sales") < order.index("agg_sales_by_category")
    store = Store(db)
    rows = {r["name"]: r for r in store.all("etl_job")}
    assert rows["m_legacy_customer_merge"]["recommendation"] == "re-engineer"
    assert rows["LoadSalesMart::DFT Load FactSales"]["rubric_version"].startswith("rubric:")
    store.close()
    assert main(["etl", "assess", str(POWERCENTER)]) == 0
    assert len(json.loads(capsys.readouterr().out)) == 5


def test_cli_schedule(tmp_path, capsys):
    db = str(tmp_path / "alt.duckdb")
    for src in (CONTROLM, SQLAGENT):
        assert main(["etl", "schedule", str(src), "--out", str(tmp_path / "sched"), "--db", db]) == 0
        report = json.loads(capsys.readouterr().out)
        assert all(r["problems"] == [] for r in report)
    files = sorted(p.name for p in (tmp_path / "sched" / "dags").glob("*.py"))
    assert len(files) == 3
    for p in (tmp_path / "sched").rglob("*.*"):
        assert is_stamped(p.read_text())
    store = Store(db)
    assert store.scalar("SELECT count(*) FROM scheduler_dag") == 2
    store.close()


def test_cli_parse_and_bi(capsys):
    assert main(["etl", "parse", str(DTSX)]) == 0
    assert "lkp_dim_product" in capsys.readouterr().out
    assert main(["etl", "bi", "power bi"]) == 0
    assert json.loads(capsys.readouterr().out)["approaches"][0]["id"] == "BI-POWERBI"
    assert main(["etl", "bi", "lotus"]) == 1


def test_generated_etl_artifacts_are_stamped_and_deterministic():
    a, b = etl_generate.generate(), etl_generate.generate()
    assert a == b and all(rel.startswith("etl/") for rel in a)
    assert all(is_stamped(c) for c in a.values())
    assert "{% macro dedupe(" in a["etl/dbt_macros/dedupe.sql"]
    assert "| SCH-06 |" in a["etl/component_mappings.md"]
