"""Read-only telemetry over the harvest-contract tables.

Agents read the same layout everywhere: a sealed diagnostic snapshot, the Package O observability
data product (whose CURATED tables follow ``altitude.synthetic.schema.HARVEST_SCHEMA``) or an
in-memory fixture (eval golden incidents). Only ``SELECT`` statements are accepted.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping

import duckdb
import sqlglot
from sqlglot import exp

from altitude.core.ids import content_hash
from altitude.synthetic.schema import HARVEST_SCHEMA

from .errors import ReadOnlyViolation

_READ_NODES = (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)
_TEXTUAL = ("JSON", "TIMESTAMP", "DATE", "VARCHAR")


def _as_text(v: Any, t: str) -> str | None:
    if v is None or isinstance(v, str):
        return v
    if t == "JSON":
        return json.dumps(v, sort_keys=True)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return str(v)


def assert_read_only(sql: str) -> None:
    """Refuse anything other than a single read-only query."""
    try:
        statements = [s for s in sqlglot.parse(sql, read="duckdb") if s is not None]
    except sqlglot.errors.ParseError as e:
        raise ReadOnlyViolation(f"telemetry query does not parse: {e}") from e
    if len(statements) != 1:
        raise ReadOnlyViolation("telemetry accepts exactly one statement per query")
    st = statements[0]
    if not isinstance(st, _READ_NODES):
        raise ReadOnlyViolation(f"telemetry is read-only; refused {type(st).__name__} statement")
    for node in st.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command,
                             exp.TruncateTable, exp.Merge)):
            raise ReadOnlyViolation(f"telemetry is read-only; refused embedded {type(node).__name__}")


class Telemetry:
    """A read-only view of harvest-contract tables with a deterministic ``as_of`` instant."""

    def __init__(self, con: duckdb.DuckDBPyConnection, as_of: datetime, ref: str, tables: list[str]):
        self._con = con
        self.as_of = as_of
        self.ref = ref
        self._tables = set(tables)

    # ------------------------------------------------------------------ constructors
    @classmethod
    def from_snapshot(cls, snapshot: Any, as_of: datetime | None = None) -> "Telemetry":
        meta = snapshot.metadata or {}
        if as_of is None and meta.get("window_end"):
            as_of = datetime.combine(date.fromisoformat(meta["window_end"]), time(23, 59, 59))
        tel = cls(snapshot.con, as_of or datetime(1970, 1, 1), snapshot.snapshot_id, snapshot.tables())
        if as_of is None and not meta.get("window_end"):
            tel.as_of = tel._derive_as_of()
        return tel

    @classmethod
    def open(cls, path: str | Path) -> "Telemetry":
        from altitude.core.snapshot import Snapshot

        return cls.from_snapshot(Snapshot.open(path, verify=True))

    @classmethod
    def from_tables(cls, tables: Mapping[str, list[Mapping[str, Any]]], as_of: datetime | str | None = None) -> "Telemetry":
        """Build an in-memory telemetry store (every harvest table exists; missing ones are empty)."""
        import pyarrow as pa

        con = duckdb.connect(":memory:")
        unknown = set(tables) - set(HARVEST_SCHEMA)
        if unknown:
            raise KeyError(f"tables outside the harvest contract: {sorted(unknown)}")
        for name, info in HARVEST_SCHEMA.items():
            cols = info["columns"]
            con.execute(f'CREATE TABLE "{name}" (' + ", ".join(f'"{c}" {t}' for c, t in cols.items()) + ")")
            rows = list(tables.get(name, []))
            if not rows:
                continue
            extra = {k for r in rows for k in r} - set(cols)
            if extra:
                raise KeyError(f"{name}: columns outside the harvest contract: {sorted(extra)}")

            arrays = {}
            for c, t in cols.items():
                values = [r.get(c) for r in rows]
                if t in _TEXTUAL:
                    arrays[c] = pa.array([_as_text(v, t) for v in values], type=pa.string())
                else:
                    arrays[c] = pa.array(values)
            arrow_tbl = pa.table(arrays)  # noqa: F841 - referenced by DuckDB replacement scan
            select = ", ".join(f'CAST("{c}" AS {t}) AS "{c}"' for c, t in cols.items())
            con.execute(f'INSERT INTO "{name}" SELECT {select} FROM arrow_tbl')
        hashes = {}
        for name in sorted(t for t in tables if tables[t]):
            hashes[name] = con.execute(
                f"SELECT md5(coalesce(string_agg(h, '' ORDER BY h), '')) "
                f'FROM (SELECT md5(CAST(t AS VARCHAR)) h FROM "{name}" t)').fetchone()[0]
        ref = "TEL-" + content_hash(hashes, 12).upper()
        tel = cls(con, datetime(1970, 1, 1), ref, list(HARVEST_SCHEMA))
        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(as_of)
        tel.as_of = as_of or tel._derive_as_of()
        return tel

    def at(self, as_of: datetime | str) -> "Telemetry":
        """The same read-only data viewed at an earlier instant (tools filter on ``as_of``)."""
        if isinstance(as_of, str):
            as_of = datetime.fromisoformat(as_of)
        return Telemetry(self._con, as_of, f"{self.ref}@{as_of.isoformat()}", sorted(self._tables))

    # ------------------------------------------------------------------ access
    def has_table(self, name: str) -> bool:
        return name in self._tables

    def query(self, sql: str, params: Mapping[str, Any] | list | None = None) -> list[dict[str, Any]]:
        assert_read_only(sql)
        cur = self._con.execute(sql, params if params is not None else [])
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def scalar(self, sql: str, params: Mapping[str, Any] | list | None = None) -> Any:
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def client_input(self, key: str, default: Any = None) -> Any:
        if not self.has_table("CLIENT_INPUTS"):
            return default
        v = self.scalar('SELECT CAST("VALUE" AS VARCHAR) FROM CLIENT_INPUTS WHERE "KEY" = ?', [key])
        return json.loads(v) if v is not None else default

    def _derive_as_of(self) -> datetime:
        candidates = []
        for table, col in (("WAREHOUSE_METERING_HISTORY", "END_TIME"), ("QUERY_HISTORY", "END_TIME"),
                           ("TASK_HISTORY", "COMPLETED_TIME"), ("DATA_QUALITY_MONITORING_RESULTS", "MEASUREMENT_TIME"),
                           ("LOGIN_HISTORY", "EVENT_TIMESTAMP"), ("WAREHOUSE_LOAD_HISTORY", "END_TIME")):
            if self.has_table(table):
                v = self._con.execute(f'SELECT max("{col}") FROM "{table}"').fetchone()[0]
                if v is not None:
                    candidates.append(v)
        if self.has_table("METERING_DAILY_HISTORY"):
            d = self._con.execute('SELECT max(USAGE_DATE) FROM METERING_DAILY_HISTORY').fetchone()[0]
            if d is not None:
                candidates.append(datetime.combine(d, time(23, 59, 59)))
        return max(candidates) if candidates else datetime(1970, 1, 1)
