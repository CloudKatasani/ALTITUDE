"""Live harvester over a fake DB-API connection: read-only statements only, exact harvest-contract snapshot."""

import json
import re

import pytest

from altitude.core.errors import ReadOnlyViolation
from altitude.diagnostics import DiagnosticsEngine
from altitude.diagnostics.harvest import CLIENT_SUPPLIED, HARVEST_QUERIES, HarvestQuery, LiveHarvester
from altitude.diagnostics.readonly import assert_read_only, parse
from altitude.synthetic.schema import HARVEST_SCHEMA

MARK = re.compile(r"/\* altitude-harvest:(\w+) \*/")


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = None
        self._rows = []

    def execute(self, sql, params=None):
        self.conn.log.append(sql)
        table = MARK.search(sql).group(1)
        if table in self.conn.fail:
            raise RuntimeError(f"SQL access control error: {table}")
        if sql.split("*/", 1)[1].strip().upper().startswith("SHOW"):
            self.description, self._rows = None, []
            return
        cols = list(HARVEST_SCHEMA[table]["columns"])
        self.description = [(c, None, None, None, None, None, None) for c in cols]
        self._rows = [tuple(r.get(c) for c in cols) for r in self.conn.tables.get(table, [])]

    def fetchall(self):
        return list(self._rows)

    def close(self):
        pass


class FakeConnection:
    """DB-API stand-in answering each harvest query with the synthetic estate's rows."""

    def __init__(self, tables, fail=()):
        self.tables = tables
        self.fail = set(fail)
        self.log: list[str] = []

    def cursor(self):
        return FakeCursor(self)


def _inputs(account):
    return {r["KEY"]: json.loads(r["VALUE"]) for r in account.tables["CLIENT_INPUTS"]}


def _harvester(account, **kw):
    return LiveHarvester(FakeConnection(account.tables, kw.pop("fail", ())), window_days=account.spec.days,
                         end=account.spec.end_date, client_inputs=kw.pop("inputs", _inputs(account)),
                         bi_reports=account.tables["BI_REPORTS"], bi_measures=account.tables["BI_MEASURES"],
                         edition=account.spec.edition, **kw)


def test_every_contract_table_has_a_read_only_query_returning_exact_columns():
    assert set(HARVEST_QUERIES) | CLIENT_SUPPLIED == set(HARVEST_SCHEMA)
    for table, q in HARVEST_QUERIES.items():
        for sql in q.statements():
            assert_read_only(sql)
        names = [n.upper() for n in parse(q.statements()[-1])[0].named_selects]
        assert names == list(HARVEST_SCHEMA[table]["columns"]), table


def test_live_harvest_reproduces_the_snapshot_and_findings(tmp_path, seeded_snapshot, seeded_result):
    snap, account = seeded_snapshot
    h = _harvester(account)
    live = h.harvest(tmp_path, snapshot_id=snap.snapshot_id)
    live.verify()
    assert live.tables() == sorted(HARVEST_SCHEMA)
    assert live.content_hash == snap.content_hash                    # same evidence ⇒ same content address
    assert all(assert_read_only(sql) is not None for sql in h.connection.log)
    assert all(st == "ok" for st in live.metadata["harvest_status"].values())
    res = DiagnosticsEngine().run(live, tier="D2")
    assert res.suggestions == seeded_result.suggestions


def test_harvester_refuses_non_read_statements_before_execution(tmp_path, seeded_snapshot, monkeypatch):
    _, account = seeded_snapshot
    h = _harvester(account)
    evil = HarvestQuery("TABLES", "DELETE FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES", "SNOWFLAKE.OBJECT_VIEWER")
    monkeypatch.setitem(HARVEST_QUERIES, "TABLES", evil)
    with pytest.raises(ReadOnlyViolation):
        h.harvest(tmp_path)
    assert not any("DELETE FROM" in sql for sql in h.connection.log)


@pytest.mark.parametrize("sql", [
    "INSERT INTO T VALUES (1)", "UPDATE T SET A = 1", "DELETE FROM T", "MERGE INTO T USING S ON T.A = S.A WHEN MATCHED THEN DELETE",
    "CREATE TABLE T (A INT)", "DROP TABLE T", "TRUNCATE TABLE T", "GRANT SELECT ON TABLE T TO ROLE R", "CALL SP()",
    "SELECT 1; DELETE FROM T", "COPY INTO T FROM @S", "SELECT SYSTEM$CANCEL_ALL_QUERIES(1)", "ALTER WAREHOUSE W SUSPEND",
    "SHOW TABLES; DROP TABLE T",
])
def test_read_only_guard(sql):
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(sql)


def test_unavailable_sources_and_missing_inputs_lower_confidence(tmp_path, seeded_snapshot, seeded_result):
    _, account = seeded_snapshot
    inputs = {k: v for k, v in _inputs(account).items() if k != "contract_price_per_credit"}
    snap = _harvester(account, fail={"ACCESS_HISTORY"}, inputs=inputs).harvest(tmp_path, snapshot_id="SNAP-PARTIAL")
    assert snap.metadata["harvest_status"]["ACCESS_HISTORY"] == "unavailable"
    res = DiagnosticsEngine().run(snap, tier="D2")
    skipped = {o.check_id for o in res.outcomes if o.status == "not_evaluated"}
    assert "DX-GOV-03" in skipped and "DX-COST-04" in skipped
    assert res.context.price_source == "rubric_default"
    full = {s["check_id"]: s["confidence"] for s in seeded_result.suggestions}
    part = {s["check_id"]: s["confidence"] for s in res.suggestions}
    assert part["DX-COST-01"] < full["DX-COST-01"]               # contract price missing ⇒ less complete evidence
    assert next(a for a in res.assumptions if a["name"] == "contract_price_per_credit")["source"].startswith("rubric.")
