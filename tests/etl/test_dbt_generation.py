"""M9 acceptance: sample packages produce dbt projects that compile and pass their generated tests
on synthetic data."""

import duckdb
import pytest
import yaml

from altitude.core.generated import is_stamped
from altitude.etl import synthetic
from altitude.etl.dbt import generate_dbt_project
from altitude.etl.harness import CompileError, DbtHarness

from .conftest import DTSX, POWERCENTER


@pytest.fixture(scope="module", params=["informatica", "ssis", "combined"])
def project(request, ssis_pkg, infa_pkg):
    pkgs = {"informatica": [infa_pkg], "ssis": [ssis_pkg], "combined": [infa_pkg, ssis_pkg]}[request.param]
    return generate_dbt_project(pkgs)


def _run(project):
    con = duckdb.connect()
    synthetic.load(con, project.sources, project.domains)
    return con, DbtHarness(project.files).run(con)


def test_project_compiles_runs_and_passes_generated_tests(project):
    con, result = _run(project)
    assert result.errors == {}
    assert set(result.built) == set(project.models)
    assert result.tests and result.failed_tests == []
    marts = [m for m in project.models.values() if m.layer == "marts"]
    assert marts
    for m in marts:  # every mart has rows on synthetic data
        assert con.execute(f"SELECT count(*) FROM analytics.{m.name}").fetchone()[0] > 0


def test_conventions_files_and_stamps(project):
    names = set(project.models)
    assert all(n.split("_")[0] in {"stg", "int", "dim", "fct", "agg"} for n in names)
    for rel, content in project.files.items():
        assert is_stamped(content), rel
    yml = {rel: yaml.safe_load(c) for rel, c in project.files.items() if rel.endswith(".yml")}
    assert any("sources" in d for d in yml.values())
    assert "dbt_project.yml" in yml and yml["dbt_project.yml"]["config-version"] == 2
    assert "models/_docs.md" in project.files


def test_informatica_project_contents(infa_pkg):
    p = generate_dbt_project([infa_pkg])
    assert {m for m in p.models if not m.startswith(("stg_", "int_"))} == {
        "dim_customer", "fct_orders", "agg_customer_sales", "fct_large_orders", "fct_cancelled_orders"}
    assert [s["job"] for s in p.skipped] == ["m_legacy_customer_merge"]
    tests = {(m.name, c.name): c.tests for m in p.models.values() for c in m.columns}
    assert tests[("dim_customer", "cust_id")][:2] == ["unique", "not_null"]
    assert tests[("dim_customer", "customer_key")][:2] == ["unique", "not_null"]          # sequence surrogate
    assert {"relationships": {"to": "ref('dim_customer')", "field": "cust_id"}} in tests[("fct_orders", "cust_id")]
    assert {"relationships": {"to": "ref('dim_customer')", "field": "cust_id"}} in tests[("agg_customer_sales", "cust_id")]
    assert {"accepted_values": {"values": ["ACTIVE", "INACTIVE", "CLOSED", "UNKNOWN"]}} in tests[("dim_customer", "status_desc")]
    assert {"accepted_values": {"values": ["LARGE", "STANDARD"]}} in tests[("fct_orders", "order_size")]
    assert {"relationships": {"to": "ref('stg_ora_sales__customers')", "field": "cust_id"}} in tests[("stg_ora_sales__orders", "cust_id")]
    int_sql = p.models["int_dim_customer"].sql
    assert "LEFT JOIN n_lkp_region_ref" in int_sql and "ROW_NUMBER() OVER" in int_sql
    assert "{{ ref('stg_ora_sales__regions') }}" in int_sql
    mart = p.files["models/marts/dim_customer.sql"]
    assert "materialized='table'" in mart and "'wf_sales_dw'" in mart and "{{ ref('int_dim_customer') }}" in mart
    route = p.models["int_fct_large_orders"].sql
    assert "COALESCE(amount >= 1000, FALSE)" in route  # router: all-match, no exclusion of other groups


def test_ssis_project_contents(ssis_pkg):
    p = generate_dbt_project([ssis_pkg])
    assert {m for m in p.models if not m.startswith(("stg_", "int_"))} == {
        "dim_product", "fct_sales", "fct_returns", "agg_sales_by_category"}
    tests = {(m.name, c.name): c.tests for m in p.models.values() for c in m.columns}
    assert tests[("dim_product", "product_key")] == ["unique", "not_null"]                # traced to inferred PK
    assert {"relationships": {"to": "ref('dim_product')", "field": "product_key"}} in tests[("fct_sales", "product_key")]
    assert tests[("agg_sales_by_category", "category")] == ["unique"]                      # sole GROUP BY column
    assert "{{ ref('dim_product') }}" in p.models["int_fct_sales"].sql                    # lookup on a generated model
    assert "{{ ref('fct_sales') }}" in p.models["int_agg_sales_by_category"].sql          # reads another job's target
    assert "NOT COALESCE(quantity < 0, FALSE)" in p.models["int_fct_sales"].sql           # first-match split
    assert p.vars == {"load_date": "2026-01-01", "rows_loaded": "0"}
    assert "macros/load_sales_mart__sql_log_start.sql" in p.files
    assert "macros/load_sales_mart__sql_truncate_fact_sales.sql" not in p.files           # retired


def test_generated_tests_catch_bad_data(infa_pkg):
    """The generated tests are real: duplicated keys and orphan facts make them fail."""
    p = generate_dbt_project([infa_pkg])
    con = duckdb.connect()
    synthetic.load(con, p.sources, p.domains)
    con.execute("INSERT INTO ora_sales.customers SELECT * FROM ora_sales.customers LIMIT 1")
    con.execute("UPDATE ora_sales.orders SET cust_id = 99999 WHERE order_id = 2")
    result = DbtHarness(p.files).run(con)
    failed = {t.name for t in result.failed_tests}
    assert "unique_dim_customer_cust_id" in failed
    assert "unique_stg_ora_sales__customers_cust_id" in failed
    assert "relationships_fct_orders_cust_id" in failed
    assert "relationships_stg_ora_sales__orders_cust_id" in failed


def test_harness_rejects_broken_projects(infa_pkg):
    p = generate_dbt_project([infa_pkg])
    files = dict(p.files)
    files["models/marts/dim_customer.sql"] = files["models/marts/dim_customer.sql"].replace("int_dim_customer", "int_missing")
    with pytest.raises(CompileError, match="int_missing"):
        DbtHarness(files).compile()
    files = dict(p.files)
    files["models/marts/_marts__models.yml"] = files["models/marts/_marts__models.yml"].replace('doc("dim_customer")', 'doc("nope")')
    with pytest.raises(CompileError, match="nope"):
        DbtHarness(files).compile()


def test_generation_is_deterministic(ssis_pkg, infa_pkg):
    from altitude.etl.informatica import parse_powercenter
    from altitude.etl.ssis import parse_dtsx

    a = generate_dbt_project([infa_pkg, ssis_pkg]).files
    b = generate_dbt_project(parse_powercenter(POWERCENTER) + [parse_dtsx(DTSX)]).files
    assert a == b
