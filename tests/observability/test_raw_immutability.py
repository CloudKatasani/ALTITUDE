"""RAW kill-test: the archive is append-only locally (guard) and in Snowflake (generated grants)."""

import re

import pytest

from altitude.core.errors import AppendOnlyViolation
from altitude.observability.db import ObsDatabase
from altitude.observability.generate import generate

MUTATIONS = [
    "UPDATE RAW.QUERY_HISTORY SET USER_NAME = 'x'",
    "update raw.warehouse_metering_history set credits_used = 0 where 1=1",
    "DELETE FROM RAW.LOGIN_HISTORY",
    "DELETE FROM obs.raw.login_history WHERE EVENT_ID = 'x'",
    "TRUNCATE RAW.TASK_HISTORY",
    "TRUNCATE TABLE RAW.TASK_HISTORY",
    "DROP TABLE RAW.USERS",
    "DROP SCHEMA RAW CASCADE",
    "ALTER TABLE RAW.USERS ADD COLUMN X INTEGER",
    "ALTER TABLE RAW.USERS RENAME TO USERS_OLD",
    "MERGE INTO RAW.USERS t USING (SELECT 'A' AS NAME) s ON t.NAME = s.NAME WHEN MATCHED THEN DELETE",
    "INSERT OVERWRITE RAW.USERS SELECT * FROM RAW.USERS",
    "INSERT OR REPLACE INTO RAW.USERS SELECT * FROM RAW.USERS",
    "CREATE OR REPLACE TABLE RAW.USERS AS SELECT 1 AS X",
    "SELECT 1; DELETE FROM RAW.HARVEST_LOG",
    "DELETE FROM RAW.SNAPSHOT_MEMBERSHIP",
    "USE RAW",
    "SET search_path = 'raw'",
    "DELETE FROM OPS.ALERT_EVENT",
    "UPDATE OPS.ROUTING_TEST SET OK = TRUE",
]


@pytest.fixture(scope="module")
def db():
    from datetime import date

    from altitude.observability.harvest import harvest_account
    from altitude.observability.sources import SyntheticSource
    from altitude.synthetic import AccountSpec

    d = ObsDatabase()
    harvest_account(d, SyntheticSource(AccountSpec(end_date=date(2026, 9, 30), days=2), native_retention_days=2),
                    date(2026, 9, 30))
    return d


@pytest.mark.parametrize("sql", MUTATIONS)
def test_raw_update_delete_is_refused(db, sql):
    before = db.scalar("SELECT count(*) FROM RAW.QUERY_HISTORY")
    with pytest.raises(AppendOnlyViolation):
        db.execute(sql)
    with pytest.raises(AppendOnlyViolation):
        db.query(sql)
    assert db.scalar("SELECT count(*) FROM RAW.QUERY_HISTORY") == before


def test_raw_cannot_be_replaced_through_the_api(db):
    with pytest.raises(AppendOnlyViolation):
        db.replace_table("RAW", "USERS", "SELECT 1 AS X")
    with pytest.raises(AppendOnlyViolation):
        db.replace_view("raw", "V", "SELECT 1 AS X")
    with pytest.raises(AppendOnlyViolation):
        db.replace_table_rows("RAW", "USERS", {"X": "INTEGER"}, [])


def test_reads_inserts_and_derived_layers_are_allowed(db):
    assert db.scalar("SELECT count(*) FROM RAW.USERS") > 0
    db.execute("CREATE OR REPLACE TABLE CURATED.SCRATCH AS SELECT 1 AS X")
    db.execute("UPDATE CURATED.SCRATCH SET X = 2")
    db.execute("DELETE FROM CURATED.SCRATCH")
    db.execute("DROP TABLE CURATED.SCRATCH")


def _grant_statements(sql: str) -> list[str]:
    body = "\n".join(l for l in sql.splitlines() if not l.lstrip().startswith("--"))
    return [s.strip() for s in body.split(";") if s.strip().upper().startswith("GRANT")]


FORBIDDEN_ON_RAW = re.compile(r"\b(UPDATE|DELETE|TRUNCATE|OWNERSHIP|ALL(\s+PRIVILEGES)?)\b(?!\s+(TABLES|VIEWS|DYNAMIC))",
                              re.IGNORECASE)


def raw_grant_problems(sql: str) -> list[str]:
    """Kill-test over generated grants: no GRANT may give UPDATE/DELETE/TRUNCATE/OWNERSHIP/ALL on RAW objects."""
    problems = []
    for st in _grant_statements(sql):
        m = re.match(r"GRANT\s+(.*?)\s+ON\s+(.*?)\s+TO\s+", st, re.IGNORECASE | re.DOTALL)
        if not m:
            continue
        privileges, target = m.group(1), m.group(2)
        if re.search(r"\bRAW\b", target, re.IGNORECASE) and FORBIDDEN_ON_RAW.search(privileges):
            problems.append(st)
    return problems


def test_generated_snowflake_grants_have_no_update_or_delete_on_raw():
    gen = generate()
    grants = gen["observability/snowflake/02_grants.sql"]
    assert raw_grant_problems(grants) == []
    raw_grants = [g for g in _grant_statements(grants) if " OBS.RAW " in f" {g} " or "SCHEMA OBS.RAW" in g]
    assert any("INSERT, SELECT ON ALL TABLES IN SCHEMA OBS.RAW TO ROLE OBS_LOADER" in g for g in raw_grants)
    assert any("FUTURE TABLES IN SCHEMA OBS.RAW" in g for g in raw_grants)
    # RAW and OPS are managed-access schemas, so object owners cannot grant around the policy
    db_sql = gen["observability/snowflake/00_database.sql"]
    assert "CREATE SCHEMA IF NOT EXISTS OBS.RAW WITH MANAGED ACCESS" in db_sql
    for f, text in gen.items():
        if f.endswith(".sql") and "grants" not in f:
            assert raw_grant_problems(text) == [], f


@pytest.mark.parametrize("bad", [
    "GRANT UPDATE ON ALL TABLES IN SCHEMA OBS.RAW TO ROLE OBS_LOADER;",
    "GRANT INSERT, DELETE ON TABLE OBS.RAW.QUERY_HISTORY TO ROLE X;",
    "GRANT ALL PRIVILEGES ON SCHEMA OBS.RAW TO ROLE X;",
    "GRANT TRUNCATE ON FUTURE TABLES IN SCHEMA OBS.RAW TO ROLE X;",
    "GRANT OWNERSHIP ON SCHEMA OBS.RAW TO ROLE X;",
])
def test_grant_kill_test_catches_violations(bad):
    assert raw_grant_problems(bad) == [bad.rstrip(";")]
