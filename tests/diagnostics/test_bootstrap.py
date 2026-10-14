"""Kill-test: the diagnostics harness runs without account-administrator roles and with no write privileges."""

import json
import re

import pytest
import sqlglot

from altitude.core.paths import generated_dir
from altitude.diagnostics.bootstrap import (
    DATABASE_ROLES, BootstrapConfig, bootstrap_sql, kill_test, permission_manifest, teardown_sql,
)
from altitude.diagnostics.harvest import CLIENT_SUPPLIED, HARVEST_QUERIES
from altitude.diagnostics.readonly import describe, parse
from altitude.synthetic.schema import HARVEST_SCHEMA


def test_bootstrap_parses_and_passes_the_kill_test():
    sql = bootstrap_sql()
    assert "ACCOUNTADMIN" not in sql.upper() and "ORGADMIN" not in sql.upper()
    statements = sqlglot.parse(sql, read="snowflake")
    assert len(statements) >= 12
    assert kill_test(sql) == []
    infos = [describe(s) for s in parse(sql)]
    grants = [i for i in infos if i.verb == "GRANT"]
    assert {i.object_name for i in grants if i.object_kind == "DATABASE ROLE"} == {f"SNOWFLAKE.{r}" for r in DATABASE_ROLES}
    assert all(i.grantee.upper().split()[-1].startswith("ALTITUDE_DIAG_") for i in grants)
    assert {i.object_name for i in infos if i.verb == "USE"} <= {"SECURITYADMIN", "SYSADMIN", "USERADMIN"}
    created = {(i.object_kind, i.object_name) for i in infos if i.verb == "CREATE"}
    assert created == {("ROLE", "ALTITUDE_DIAG_ROLE"), ("WAREHOUSE", "ALTITUDE_DIAG_WH"),
                       ("RESOURCE MONITOR", "ALTITUDE_DIAG_RM"), ("USER", "ALTITUDE_DIAG_SVC")}
    assert "WAREHOUSE_SIZE = 'XSMALL'" in sql and "RSA_PUBLIC_KEY" in sql
    assert not re.search(r"(?i)\bPASSWORD\s*=", sql), "the service user must not have a password"


def test_credit_cap_comes_from_the_rubric():
    from altitude.core.rubric import default_rubrics

    budget = default_rubrics().get("rubric.diagnostics.access.credit_budget")
    assert f"CREDIT_QUOTA = {float(budget):g}" in bootstrap_sql()
    assert "CREDIT_QUOTA = 12" in bootstrap_sql(BootstrapConfig(credit_budget=12))


@pytest.mark.parametrize("injection", [
    "USE ROLE ACCOUNTADMIN;",
    "GRANT ROLE ACCOUNTADMIN TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT INSERT ON TABLE EDW.SALES.FCT_ORDERS TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT SELECT ON ALL TABLES IN SCHEMA EDW.SALES TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT OWNERSHIP ON DATABASE EDW TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT USAGE ON WAREHOUSE WH_BI_PROD TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE ALTITUDE_DIAG_ROLE;",
    "GRANT ROLE SYSADMIN TO USER ALTITUDE_DIAG_SVC;",
    "GRANT MONITOR USAGE ON ACCOUNT TO ROLE ANALYST;",
    "CREATE TABLE EDW.SALES.SCRATCH (A INT);",
    "DELETE FROM EDW.SALES.FCT_ORDERS;",
    "DROP TABLE EDW.SALES.FCT_ORDERS;",
])
def test_kill_test_rejects_privilege_escalation_and_writes(injection):
    assert kill_test(bootstrap_sql() + injection + "\n"), injection


def test_permission_manifest_explains_every_privilege():
    m = permission_manifest()
    privs = m["privileges"]
    assert privs and all(p["why"] and p["read_only"] for p in privs)
    statements = {p["statement"] for p in privs}
    for line in bootstrap_sql().splitlines():
        if line.startswith("GRANT "):
            assert line.rstrip(";") in statements, f"grant without a manifest entry: {line}"
    unlocked = {t for tables in m["evidence_unlocked"].values() for t in tables}
    assert unlocked | set(m["client_supplied"]) == set(HARVEST_SCHEMA)
    assert set(m["client_supplied"]) == CLIENT_SUPPLIED
    assert any("administrator" in x for x in m["never_requested"])


def test_teardown_revokes_everything_the_bootstrap_granted():
    td = teardown_sql()
    assert "ACCOUNTADMIN" not in td.upper()
    for role in DATABASE_ROLES:
        assert f"REVOKE DATABASE ROLE SNOWFLAKE.{role} FROM ROLE ALTITUDE_DIAG_ROLE" in td
    for obj in ("DROP USER IF EXISTS ALTITUDE_DIAG_SVC", "DROP ROLE IF EXISTS ALTITUDE_DIAG_ROLE",
                "DROP WAREHOUSE IF EXISTS ALTITUDE_DIAG_WH", "DROP RESOURCE MONITOR IF EXISTS ALTITUDE_DIAG_RM"):
        assert obj in td
    assert "LOGIN_HISTORY" in td and "QUERY_HISTORY" in td  # access log handed to the client
    assert sqlglot.parse(td, read="snowflake")


def test_generated_access_package_is_committed_and_compliant():
    gen = generated_dir() / "diagnostics"
    sql = (gen / "bootstrap.sql").read_text()
    assert kill_test(sql) == []
    manifest = json.loads((gen / "permission_manifest.json").read_text())
    assert manifest["principal"]["role"] == "ALTITUDE_DIAG_ROLE"


def test_every_harvest_query_targets_a_role_granted_by_the_bootstrap():
    granted = {f"SNOWFLAKE.{r}" for r in DATABASE_ROLES} | {"MONITOR USAGE", "MONITOR EXECUTION", "(session context)"}
    for t, q in HARVEST_QUERIES.items():
        assert q.database_role in granted or q.database_role.endswith("(optional)"), t
