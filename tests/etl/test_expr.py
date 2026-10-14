import duckdb
import pytest
import sqlglot

from altitude.etl.expr import UnsupportedExpression, translate


@pytest.mark.parametrize("expr, sql", [
    ('UPPER(TRIM([First Name])) + " " + LastName', "UPPER(TRIM(first_name)) || ' ' || last_name"),
    ('ISNULL(Region) ? "UNKNOWN" : (DT_WSTR,10)Region',
     "CASE WHEN (region IS NULL) THEN 'UNKNOWN' ELSE CAST(region AS VARCHAR(10)) END"),
    ('Amount > 1000 && Status == "SHIPPED" || !IsTest', "((amount > 1000) AND (status = 'SHIPPED')) OR NOT (is_test)"),
    ("(DT_NUMERIC,18,2)(Quantity * UnitPrice)", "CAST(quantity * unit_price AS DECIMAL(18,2))"),
    ('DATEADD("dd", -1, GETDATE())', "DATEADD(day, -(1), CURRENT_TIMESTAMP())"),
    ("REPLACENULL(Discount, 0) + LEN(Code)", "COALESCE(discount, 0) + LENGTH(code)"),
])
def test_ssis_expressions(expr, sql):
    assert translate(expr, "ssis").sql == sql


@pytest.mark.parametrize("expr, sql", [
    ("IIF(ISNULL(CUST_NAME), 'UNKNOWN', LTRIM(RTRIM(CUST_NAME)))",
     "CASE WHEN (cust_name IS NULL) THEN 'UNKNOWN' ELSE LTRIM(RTRIM(cust_name)) END"),
    ("DECODE(TRUE, AMOUNT > 1000, 'HIGH', AMOUNT > 100, 'MEDIUM', 'LOW')",
     "CASE WHEN amount > 1000 THEN 'HIGH' WHEN amount > 100 THEN 'MEDIUM' ELSE 'LOW' END"),
    ("DECODE(STATUS, 'A', 'ACTIVE', 'UNKNOWN')", "CASE WHEN status = 'A' THEN 'ACTIVE' ELSE 'UNKNOWN' END"),
    ("FIRST_NAME || ' ' || LAST_NAME", "first_name || ' ' || last_name"),
    ("ADD_TO_DATE(ORDER_DATE, 'DD', 30)", "DATEADD(day, 30, order_date)"),
    ("NOT ISNULL(X) AND Y != 0", "NOT ((x IS NULL)) AND (y <> 0)"),
    ("SYSDATE", "CURRENT_TIMESTAMP()"),
    ("TO_DECIMAL(AMT, 2) * 100 -- percent", "CAST(amt AS DECIMAL(38, 2)) * 100"),
])
def test_informatica_expressions(expr, sql):
    assert translate(expr, "informatica").sql == sql


def test_literal_values_comparisons_and_aggregates():
    t = translate("DECODE(STATUS, 'A', 'ACTIVE', 'I', 'INACTIVE', 'UNKNOWN')", "informatica")
    assert t.literal_values == ["ACTIVE", "INACTIVE", "UNKNOWN"]
    assert t.comparisons == [("status", "A"), ("status", "I")]
    assert translate("SUM(AMOUNT)", "informatica").is_aggregate
    assert translate('Qty > 0 ? "S" : "R"', "ssis").literal_values == ["S", "R"]


def test_variables_resolver_and_types():
    t = translate("@[User::LoadDate]", "ssis", var_types={"load_date": "timestamp"})
    assert t.sql == "CAST('{{ var(\"load_date\") }}' AS TIMESTAMP)" and t.variables == {"load_date"}
    assert translate("$$BATCH_ID + 1", "informatica", var_types={"batch_id": "number"}).sql == '{{ var("batch_id") }} + 1'
    t = translate("AMOUNT * 2", "informatica", resolve=lambda c: "src.amount - src.discount")
    assert t.sql == "(src.amount - src.discount) * 2"


@pytest.mark.parametrize("expr, tool", [
    (":LKP.LKP_CUSTOMER(CUST_ID)", "informatica"),
    ("SOUNDEX(NAME)", "informatica"),
    ("IIF(A)", "informatica"),
    ('TOKEN(Name, " ", 1)', "ssis"),
    ("A +", "ssis"),
])
def test_unsupported_expressions_raise(expr, tool):
    with pytest.raises(UnsupportedExpression):
        translate(expr, tool)


def test_translations_are_valid_snowflake_and_run_in_duckdb():
    exprs = [("IIF(ISNULL(A), 'X', UPPER(LTRIM(RTRIM(A))))", "informatica"),
             ("ROUND(B * (1 - IIF(ISNULL(C), 0, C) / 100), 2)", "informatica"),
             ('LEN(TRIM(A)) == 0 ? "EMPTY" : SUBSTRING(A, 1, 2)', "ssis"),
             ("ADD_TO_DATE(D, 'DD', 30)", "informatica")]
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT ' ab ' AS a, 12.5::DECIMAL(10,2) AS b, NULL::DECIMAL(5,2) AS c, DATE '2026-01-01' AS d")
    for text, tool in exprs:
        sql = f"SELECT {translate(text, tool).sql} FROM t"
        duck = sqlglot.transpile(sql, read="snowflake", write="duckdb")[0]
        assert con.execute(duck).fetchone() is not None
