import csv
import io
import json
import re

from altitude.assessment.report import export_report, render
from altitude.cli import main
from altitude.core.theme import tokens


def test_report_exports_from_snapshot_are_themed_and_deterministic(mssql_assessment, tmp_path):
    a = export_report(mssql_assessment, tmp_path / "a")
    b = export_report(mssql_assessment.snapshot.path, tmp_path / "b")
    for fmt in ("md", "html", "csv"):
        assert a[fmt].read_text() == b[fmt].read_text()  # byte-identical from the same snapshot
    md, html = a["md"].read_text(), a["html"].read_text()
    t = tokens()
    assert t["PRODUCT_NAME"] in md and t["COMPANY_NAME"] in md and t["COLOR_PRIMARY"] in html
    assert not re.search(r"\{\{|\{%", md + html)  # every placeholder rendered
    assert mssql_assessment.snapshot_id in md and mssql_assessment.rubric_version in md
    assert "SalesDW.rpt.vw_ProductMargin" in md.split("## Awaiting review")[1].split("## Retire")[0]
    assert "Not assessed: altitude.patterns" in md
    assert "<script" not in html and "&lt;" not in md


def test_partner_theme_changes_branding_only(mssql_assessment):
    default = render(mssql_assessment, "md")
    partner = render(mssql_assessment, "md", theme="partner_example")
    p = tokens("partner_example")
    assert p["PRODUCT_NAME"] in partner and tokens()["PRODUCT_NAME"] not in partner
    strip = lambda s, t: s.replace(t["COMPANY_NAME"], "Y").replace(t["PRODUCT_NAME"], "X").replace(  # noqa: E731
        t["SUPPORT_EMAIL"], "Z")
    assert strip(default, tokens()) == strip(partner, p)


def test_csv_inventory_lists_every_object(mssql_assessment):
    rows = list(csv.DictReader(io.StringIO(render(mssql_assessment, "csv"))))
    assert len(rows) == mssql_assessment.summary["objects"]
    by = {r["fq_name"]: r for r in rows}
    assert by["SalesDW.dbo.vw_LegacyBudget"]["disposition"] == "retire"
    assert by["SalesDW.rpt.vw_ProductMargin"]["needs_review"] == "True"
    assert by["SalesDW.etl.usp_LoadDimProduct"]["complexity_band"] == "high"


def test_cli_run_and_report(harvests, tmp_path, capsys, no_drift):
    rc = no_drift(main, ["assess", "run", "--harvest", str(harvests["teradata"].path), "--out", str(tmp_path / "s"),
                         "--store", str(tmp_path / "store.duckdb"), "--report", str(tmp_path / "r")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["drift_scan"] == "skipped" and (tmp_path / "r" / "inventory.csv").exists()
    assert main(["assess", "report", "--snapshot", out["path"], "--out", str(tmp_path / "r2")]) == 0
    capsys.readouterr()
    assert main(["assess", "review", "--store", str(tmp_path / "store.duckdb")]) == 0
    items = json.loads(capsys.readouterr().out)
    assert len(items) >= out["review_items"]
