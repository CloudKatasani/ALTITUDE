"""The check catalogue is data: complete, schema-valid, rubric-bound, and free of threshold literals."""

import re

import jinja2
import pytest
import sqlglot
from sqlglot import exp

from altitude.core.rubric import default_rubrics
from altitude.diagnostics import default_catalogue
from altitude.diagnostics import formula
from altitude.diagnostics.catalogue import PARAM_RE, STANDARD_PARAMS
from altitude.synthetic.schema import HARVEST_SCHEMA
from altitude.synthetic.snowflake_account import ALL_ISSUES

from diag_testdata import KPI_IDS

CAT = default_catalogue()
CHECKS = CAT.checks
FORMULA_VARS = {"price_per_credit", "storage_price_per_tb_month", "annualise", "months_per_year"}


def _tables_in(sql: str) -> set[str]:
    text = PARAM_RE.sub("NULL", sql)
    tree = sqlglot.parse_one(text, read="duckdb")
    ctes = {c.alias_or_name.upper() for c in tree.find_all(exp.CTE)}
    names = {t.name.upper() for t in tree.find_all(exp.Table) if t.name}
    return names - ctes


def test_all_33_section_6_4_checks_are_implemented():
    assert [c.id for c in CHECKS] == sorted(ALL_ISSUES)
    assert len(CHECKS) == 33


def test_ten_domains_five_pillars_and_tiers():
    assert [d["id"] for d in CAT.domains] == [f"D{i}" for i in range(1, 11)]
    assert {p["pillar"] for p in CAT.pillars} == {"security_governance", "operational_excellence", "reliability",
                                                  "performance_efficiency", "cost_optimization"}
    assert [t["tier"] for t in CAT.tiers] == ["D0", "D1", "D2", "D3"]
    d0 = CAT.tier("D0")
    assert d0["domains"] == ["D1", "D2", "D3", "D4", "D5"] and d0["top_findings"] == 10
    assert {d for c in CHECKS for d in c.scored_domains} == {f"D{i}" for i in range(1, 11)}


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_detector_reads_only_declared_contract_tables(check):
    helpers = {h["name"].upper() for h in CAT.helpers}
    used = _tables_in(check.detector_sql()) - helpers
    assert used <= set(HARVEST_SCHEMA), f"{check.id} reads tables outside the harvest contract: {used - set(HARVEST_SCHEMA)}"
    for h in CAT.helpers:
        if h["kind"] == "view" and h["name"] in check.detector["signals"]:
            used |= _tables_in(h["sql"])
    undeclared = used - set(check.requires) - {"CLIENT_INPUTS"}
    assert not undeclared, f"{check.id}: undeclared source tables {sorted(undeclared)}"


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_thresholds_are_parameters_never_literals(check):
    rubrics = default_rubrics()
    for part in (check.detector["signals"], check.detector["rule"]):
        tree = sqlglot.parse_one(PARAM_RE.sub("NULL", f"SELECT {part}" if part is check.detector["rule"] else part),
                                 read="duckdb")
        literals = {lit.this for lit in tree.find_all(exp.Literal) if lit.is_number}
        assert literals <= {"0", "1"}, f"{check.id}: numeric literal(s) {literals} in detector; bind a rubric parameter"
    params = check.resolve_params(rubrics)
    for name in check.referenced_params():
        assert name in params or name in STANDARD_PARAMS, f"{check.id}: ${name} is not bound"
    for name, spec in check.detector["params"].items():
        if "value" in spec:
            assert not isinstance(spec["value"], (int, float)), f"{check.id}.{name}: numeric value must be a rubric ref"


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_value_or_risk_model_and_remediation_with_rollback(check):
    raw = check.raw
    assert raw["value"]["method"]
    assert raw["value"].get("p50") or raw.get("risk"), f"{check.id} needs a $ value model or a risk model"
    if raw["value"].get("p50"):
        for key in ("p50", "conservative"):
            names = formula.names(raw["value"][key])
            unknown = {n for n in names if not n.isupper()} - FORMULA_VARS - set(raw["value"].get("factors", {}))
            assert not unknown, f"{check.id} formula uses undefined variables {unknown}"
        with pytest.raises(formula.FormulaError):
            formula.evaluate("IDLE * 0.7", {"IDLE": 1})
    env = jinja2.Environment()
    for key in ("title_template", "rationale_template"):
        env.parse(raw[key])
    env.parse(raw["remediation"]["template"])
    env.parse(raw["remediation"]["rollback"])
    assert raw["remediation"]["autonomy"] in {"L0", "L1", "L2", "L3"}
    assert set(raw["kpis_to_watch"]) <= KPI_IDS
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw["last_verified"])
    assert set(raw["evidence"]["fields"]), "evidence spec lists the signals kept as evidence"


def test_recommender_rules_reference_known_checks_and_domains():
    ids = {c.id for c in CHECKS}
    for rule in CAT.recommendations:
        assert set(rule["when"].get("checks_any", [])) <= ids
        assert set(rule["when"].get("domains_any", [])) <= {d["id"] for d in CAT.domains}
