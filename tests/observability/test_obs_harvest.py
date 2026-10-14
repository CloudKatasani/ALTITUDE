"""Config-driven multi-account harvest; history retained beyond the native retention window."""

from datetime import date, datetime, timedelta

import pytest

from altitude.core.errors import ReadOnlyViolation
from altitude.observability.config import load_registry, load_sources
from altitude.observability.curate import build_curated
from altitude.observability.db import ObsDatabase
from altitude.observability.harvest import harvest_account, harvest_registry
from altitude.observability.sources import SnowflakeSource, SyntheticSource, assert_read_only, live_statements
from altitude.synthetic import AccountSpec, generate
from altitude.synthetic.schema import HARVEST_SCHEMA

RETENTION = 10
D1, D2 = date(2026, 9, 24), date(2026, 9, 30)  # overlapping 10-day windows


def _harvest(db, end, **kw):
    spec = AccountSpec(end_date=end, days=RETENTION, **kw)
    return harvest_account(db, SyntheticSource(spec, native_retention_days=RETENTION), end)


@pytest.fixture(scope="module")
def two_harvests():
    db = ObsDatabase()
    r1 = _harvest(db, D1)
    r2 = _harvest(db, D2)
    return db, r1, r2


def test_sources_config_covers_the_harvest_contract():
    cfgs = load_sources()
    assert {c.table for c in cfgs} == set(HARVEST_SCHEMA)
    assert {c.strategy for c in cfgs} == {"incremental", "merge", "full_snapshot"}
    for c in cfgs:
        if c.strategy != "full_snapshot":
            assert c.watermark in HARVEST_SCHEMA[c.table]["columns"] and c.native_retention_days


def test_history_is_retained_beyond_the_native_retention_window(two_harvests):
    db, r1, r2 = two_harvests
    assert r1.ok and r2.ok
    days = [r["D"] for r in db.query(
        "SELECT DISTINCT CAST(START_TIME AS DATE) AS D FROM RAW.WAREHOUSE_METERING_HISTORY ORDER BY 1")]
    # the second source can only show D2-9..D2; the archive keeps the union of both windows
    source2_start = D2 - timedelta(days=RETENTION - 1)
    assert days[0] == D1 - timedelta(days=RETENTION - 1)
    assert days[-1] == D2
    assert any(d < source2_start for d in days), "rows older than the source window were kept"
    assert len(days) == (D2 - days[0]).days + 1

    # the archive equals the union of what the two windows exposed — no more, no less
    a = generate(AccountSpec(end_date=D1, days=RETENTION)).tables["WAREHOUSE_METERING_HISTORY"]
    b = generate(AccountSpec(end_date=D2, days=RETENTION)).tables["WAREHOUSE_METERING_HISTORY"]
    union = {(r["WAREHOUSE_NAME"], r["START_TIME"]) for r in a + b}
    archived = {(r["WAREHOUSE_NAME"], r["START_TIME"]) for r in db.query(
        "SELECT WAREHOUSE_NAME, START_TIME FROM RAW.WAREHOUSE_METERING_HISTORY")}
    assert archived == union


@pytest.mark.parametrize("table,key", [
    ("WAREHOUSE_METERING_HISTORY", "WAREHOUSE_NAME, START_TIME"),
    ("QUERY_HISTORY", "QUERY_ID"),
    ("LOGIN_HISTORY", "EVENT_ID"),
    ("METERING_DAILY_HISTORY", "USAGE_DATE, SERVICE_TYPE"),
    ("TASK_HISTORY", "FQ_NAME, RUN_ID"),
])
def test_no_duplicates_after_overlapping_harvests(two_harvests, table, key):
    db, _, r2 = two_harvests
    assert db.scalar(f"SELECT count(*) - count(DISTINCT _ROW_HASH) FROM RAW.{table}") == 0
    assert db.scalar(f"SELECT count(*) FROM (SELECT {key} FROM RAW.{table} GROUP BY {key} HAVING count(*) > 1)") == 0
    step = next(s for s in r2.steps if s["SOURCE_TABLE"] == table)
    assert step["ROWS_DUPLICATE"] > 0, "the overlap re-read was de-duplicated, not re-inserted"


def test_rerunning_a_harvest_is_idempotent(two_harvests):
    db, _, _ = two_harvests
    before = {t: db.scalar(f'SELECT count(*) FROM RAW."{t}"') for t in HARVEST_SCHEMA}
    members = db.scalar("SELECT count(*) FROM RAW.SNAPSHOT_MEMBERSHIP")
    again = _harvest(db, D2)
    assert again.inserted == 0
    assert {t: db.scalar(f'SELECT count(*) FROM RAW."{t}"') for t in HARVEST_SCHEMA} == before
    assert db.scalar("SELECT count(*) FROM RAW.SNAPSHOT_MEMBERSHIP") == members


def test_every_archived_row_carries_account_name_and_load_metadata(two_harvests):
    db, _, _ = two_harvests
    for t in HARVEST_SCHEMA:
        cols = [r["column_name"] for r in db.query(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'RAW' AND table_name = ?", [t])]
        assert {"ACCOUNT_NAME", "_ROW_HASH", "_HARVEST_ID", "_LOADED_AT"} <= set(cols)
        assert db.scalar(f'SELECT count(*) FROM RAW."{t}" WHERE ACCOUNT_NAME IS NULL OR _ROW_HASH IS NULL') == 0


def test_full_snapshots_reconstruct_each_harvest_day(two_harvests):
    db, _, _ = two_harvests
    build_curated(db)
    days = [r["SNAPSHOT_DATE"] for r in db.query("SELECT DISTINCT SNAPSHOT_DATE FROM CURATED.SNAP_USERS ORDER BY 1")]
    assert days == [D1, D2]
    # LAST_SUCCESS_LOGIN moves with the harvest day: each day's snapshot shows its own state, not a union
    for d in days:
        users = db.query("SELECT NAME, LAST_SUCCESS_LOGIN FROM CURATED.SNAP_USERS WHERE SNAPSHOT_DATE = ?", [d])
        assert len(users) == len({u["NAME"] for u in users}) == len(generate(AccountSpec(end_date=d, days=1)).tables["USERS"])
    latest = db.query("SELECT DISTINCT SNAPSHOT_DATE FROM CURATED.SNAP_USERS WHERE IS_LATEST")
    assert [r["SNAPSHOT_DATE"] for r in latest] == [D2]


def test_multi_account_registry_harvest():
    db = ObsDatabase()
    reg = load_registry()
    results = harvest_registry(db, reg, date(2026, 9, 30), days=5, native_retention_days=5)
    assert [r.account_name for r in results] == [a["account_name"] for a in reg["accounts"]]
    assert all(r.ok for r in results)
    accts = {r["ACCOUNT_NAME"] for r in db.query("SELECT DISTINCT ACCOUNT_NAME FROM RAW.WAREHOUSE_METERING_HISTORY")}
    assert accts == {"ACME_PROD", "ACME_DEV"}
    # identical-looking rows from different accounts are distinct archive rows
    assert db.scalar("SELECT count(DISTINCT _ROW_HASH) FROM RAW.ROLES") == db.scalar("SELECT count(*) FROM RAW.ROLES")


# --------------------------------------------------------------------------- live harvest (fake DB-API connection)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        self.conn.executed.append((sql, params))
        table = self.conn.by_sql[sql]
        if table in self.conn.fail:
            raise RuntimeError(f"simulated failure reading {table}")
        if sql.lstrip().upper().startswith("SHOW"):
            self.description, self._rows = [("name",)], []
            return
        cols = list(HARVEST_SCHEMA[table]["columns"])
        self.description = [(c.lower(), None) for c in cols]  # drivers may return lower-case names
        self._rows = [tuple(r.get(c) for c in cols) for r in self.conn.account.tables[table]]

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self, fail=()):
        self.account = generate(AccountSpec(end_date=date(2026, 9, 30), days=3))
        self.executed = []
        self.fail = set(fail)
        self.by_sql = {}
        for cfg in load_sources():
            for st in live_statements(cfg):
                self.by_sql[st] = cfg.table

    def cursor(self):
        return FakeCursor(self)


def test_live_harvest_reads_only_through_select_and_show():
    conn = FakeConnection()
    db = ObsDatabase()
    src = SnowflakeSource(conn, "LIVE_PROD")
    res = harvest_account(db, src, datetime(2026, 9, 30, 23, 59, 59))
    assert res.ok
    assert conn.executed
    for sql, params in conn.executed:
        assert sql.lstrip().upper().startswith(("SELECT", "SHOW"))
        if "%(since)s" in sql:
            assert isinstance(params, dict) and isinstance(params["since"], datetime)
    skipped = {s["SOURCE_TABLE"] for s in res.steps if s["STATUS"] == "skipped"}
    assert skipped == {"CLIENT_INPUTS", "BI_REPORTS", "BI_MEASURES"}  # client-supplied, not read from Snowflake
    assert db.scalar("SELECT count(*) FROM RAW.QUERY_HISTORY WHERE ACCOUNT_NAME = 'LIVE_PROD'") == \
        len(conn.account.tables["QUERY_HISTORY"])
    # the incremental watermark drives the next read
    conn.executed.clear()
    harvest_account(db, src, datetime(2026, 10, 1, 23, 0))
    since = [p["since"] for sql, p in conn.executed if p and "WAREHOUSE_METERING_HISTORY" in sql][0]
    assert since > datetime(2026, 9, 1)


def test_live_harvest_logs_a_failing_source_and_continues():
    conn = FakeConnection(fail={"LOGIN_HISTORY"})
    db = ObsDatabase()
    res = harvest_account(db, SnowflakeSource(conn, "LIVE_PROD"), datetime(2026, 9, 30, 23, 0))
    failed = [s for s in res.steps if s["STATUS"] == "failed"]
    assert [s["SOURCE_TABLE"] for s in failed] == ["LOGIN_HISTORY"] and "simulated failure" in failed[0]["ERROR"]
    assert db.scalar("SELECT count(*) FROM RAW.HARVEST_LOG WHERE STATUS = 'failed'") == 1
    assert db.scalar("SELECT count(*) FROM RAW.WAREHOUSE_METERING_HISTORY") > 0


@pytest.mark.parametrize("sql", [
    "DELETE FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY",
    "SELECT 1; DROP TABLE X",
    "INSERT INTO T SELECT 1",
    "CREATE TABLE T AS SELECT 1",
    "SELECT * FROM T WHERE 1=1 UNION ALL SELECT * FROM (UPDATE T SET A = 1)",
    "CALL SYSTEM$CANCEL_ALL_QUERIES()",
    "GRANT ROLE ACCOUNTADMIN TO USER X",
])
def test_live_harvest_kill_test(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_every_configured_live_statement_is_read_only():
    for cfg in load_sources():
        for st in live_statements(cfg):
            assert_read_only(st)
