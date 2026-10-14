"""Harvest sources: anything that can read harvest-contract tables for one account.

- :class:`SyntheticSource` wraps :mod:`altitude.synthetic` and *simulates the native retention window*:
  an incremental source only exposes rows from the last ``native_retention_days`` before ``as_of``.
- :class:`SnowflakeSource` reads a live account through any DB-API 2.0 connection. It is read-only by
  construction: it only ever executes ``SELECT`` / ``SHOW`` statements (anything else raises
  :class:`~altitude.core.errors.ReadOnlyViolation`) built from ``knowledge/observability/sources.yaml``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Protocol

from altitude.core.errors import ReadOnlyViolation
from altitude.synthetic.schema import HARVEST_SCHEMA

from .config import SourceConfig, sources_defaults


class HarvestSource(Protocol):
    account_name: str

    def read(self, cfg: SourceConfig, *, since: datetime | None, as_of: datetime) -> list[dict] | None:
        """Rows for ``cfg.table`` visible at ``as_of`` (and at/after ``since`` for incremental sources).

        ``None`` means the source does not provide this table (e.g. client-supplied inputs on a live account).
        """
        ...


def _as_dt(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None)
    if isinstance(v, date):
        return datetime.combine(v, time())
    return datetime.fromisoformat(str(v))


def retention_start(cfg: SourceConfig, as_of: datetime, override_days: int | None = None) -> datetime | None:
    days = override_days if override_days is not None else cfg.native_retention_days
    if not days:
        return None
    return datetime.combine(as_of.date() - timedelta(days=days - 1), time())


# --------------------------------------------------------------------------- synthetic


@dataclass
class SyntheticSource:
    """A synthetic account observed at ``spec.end_date`` with a simulated native retention window.

    ``native_retention_days`` overrides every source's configured retention (tests use a short window).
    """

    spec: Any  # altitude.synthetic.AccountSpec
    native_retention_days: int | None = None
    _account: Any = field(default=None, init=False, repr=False)

    @property
    def account_name(self) -> str:
        return self.spec.account_name

    @property
    def account(self):
        if self._account is None:
            from altitude.synthetic import generate

            spec = self.spec
            if self.native_retention_days:
                spec = replace(spec, days=max(1, min(spec.days, self.native_retention_days)))
            self._account = generate(spec)
        return self._account

    def read(self, cfg: SourceConfig, *, since: datetime | None, as_of: datetime) -> list[dict] | None:
        rows = self.account.tables.get(cfg.table, [])
        if cfg.is_snapshot or not cfg.watermark:
            return [dict(r) for r in rows]
        lo = retention_start(cfg, as_of, self.native_retention_days)
        if since is not None:
            lo = max(lo, since) if lo else since
        hi = as_of
        out = []
        for r in rows:
            wm = _as_dt(r.get(cfg.watermark))
            if wm is None or wm > hi or (lo is not None and wm < lo):
                continue
            out.append(dict(r))
        return out


# --------------------------------------------------------------------------- live Snowflake

_READ_ONLY = re.compile(r"^\s*(SELECT|SHOW|WITH|DESCRIBE|DESC)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|CALL|EXECUTE|PUT|COPY|UNDROP|USE)\b",
    re.IGNORECASE,
)


def assert_read_only(sql: str) -> None:
    """Refuse anything that is not a single read-only statement (live harvest kill-test)."""
    body = sql.strip().rstrip(";")
    stripped = re.sub(r"'(?:[^']|'')*'", "''", body)
    if ";" in stripped or not _READ_ONLY.match(stripped):
        raise ReadOnlyViolation(f"live harvest only issues single SELECT/SHOW statements: {sql[:80]!r}")
    if not stripped.upper().lstrip().startswith("SHOW") and _FORBIDDEN.search(stripped):
        raise ReadOnlyViolation(f"live harvest statement contains a write verb: {sql[:80]!r}")


def live_statements(cfg: SourceConfig, defaults: dict | None = None) -> list[str]:
    """The read-only statements the live harvester issues for ``cfg`` (last one returns the rows)."""
    defaults = defaults or sources_defaults()
    live = cfg.live or {}
    cols = list(HARVEST_SCHEMA[cfg.table]["columns"])
    if live.get("origin"):
        return []
    if "sql" in live:
        return [live["sql"].strip()]
    if "view" in live:
        fq = f"{defaults.get('database', 'SNOWFLAKE')}.{defaults.get('schema', 'ACCOUNT_USAGE')}.{live['view']}"
        sql = f"SELECT {', '.join(cols)} FROM {fq}"
        if live.get("where"):
            sql += f" WHERE {live['where']}"
        elif cfg.watermark and not cfg.is_snapshot:
            sql += f" WHERE {cfg.watermark} >= %(since)s"
        return [sql]
    if "show" in live:
        mapping = live.get("columns") or {}
        select = ", ".join(f"{mapping.get(c, 'NULL')} AS {c}" for c in cols)
        return [live["show"], f"SELECT {select} FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"]
    raise ValueError(f"source {cfg.table}: live harvest is not configured")


@dataclass
class SnowflakeSource:
    """Live account over a DB-API connection (e.g. ``snowflake.connector.connect(...)``)."""

    connection: Any
    account_name: str
    executed: list[str] = field(default_factory=list)

    def read(self, cfg: SourceConfig, *, since: datetime | None, as_of: datetime) -> list[dict] | None:
        statements = live_statements(cfg)
        if not statements:
            return None
        lo = since or retention_start(cfg, as_of) or datetime(1970, 1, 1)
        cur = self.connection.cursor()
        try:
            for i, sql in enumerate(statements):
                assert_read_only(sql)
                self.executed.append(sql)
                if "%(since)s" in sql:
                    cur.execute(sql, {"since": lo})
                else:
                    cur.execute(sql)
            names = [d[0].upper() for d in (cur.description or [])]
            fetched = cur.fetchall()
        finally:
            close = getattr(cur, "close", None)
            if close:
                close()
        contract = list(HARVEST_SCHEMA[cfg.table]["columns"])
        rows = []
        for rec in fetched:
            raw = dict(zip(names, rec)) if not isinstance(rec, dict) else {k.upper(): v for k, v in rec.items()}
            row = {c: raw.get(c) for c in contract}
            wm = _as_dt(row.get(cfg.watermark)) if cfg.watermark else None
            if wm is not None and wm > as_of:
                continue
            rows.append(row)
        return rows
