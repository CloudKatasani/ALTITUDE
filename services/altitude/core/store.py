"""Control-plane store for the canonical data model.

PostgreSQL 16 is the SaaS target; this module provides the same model on
DuckDB for local, CI and in-boundary use. Migrations are written once in the
PostgreSQL dialect (``migrations/*.sql``) and transpiled with sqlglot.

Append-only tables (snapshots, audit, approvals, agent actions, validation
runs, gate decisions) reject UPDATE/DELETE/TRUNCATE/DROP here *and* through
triggers on PostgreSQL — principle 5 ("immutable, keyed snapshots").

Modules may add their own migrations by placing ``NNNN_<module>.sql`` files in
any directory registered with :func:`register_migration_dir`.
"""

from __future__ import annotations

import json
import threading
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb
import sqlglot
from sqlglot import exp

from .errors import AppendOnlyViolation

MIGRATION_DIRS: list[Path] = [Path(__file__).parent / "migrations"]

APPEND_ONLY: set[str] = {
    "snapshot",
    "audit_event",
    "approval",
    "agent_action",
    "validation_run",
    "gate",
}


def register_migration_dir(path: Path) -> None:
    if path not in MIGRATION_DIRS:
        MIGRATION_DIRS.append(path)


def register_append_only(*tables: str) -> None:
    APPEND_ONLY.update(t.lower() for t in tables)


def _migration_files() -> list[Path]:
    files: list[Path] = []
    for d in MIGRATION_DIRS:
        files.extend(d.glob("*.sql"))
    return sorted(files, key=lambda p: (p.name, str(p)))


def _to_db(value: Any) -> Any:
    if isinstance(value, (dict,)):
        return json.dumps(value, sort_keys=True, default=str)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return json.dumps(value, sort_keys=True, default=str)
    return value


def _mutated_tables(sql: str) -> list[tuple[str, str]]:
    """Return (operation, table) for every mutating statement in ``sql``."""
    out: list[tuple[str, str]] = []
    try:
        statements = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError:
        # Unparseable statements are refused if they mention an append-only table with a mutating verb.
        low = sql.lower()
        for t in APPEND_ONLY:
            if t in low and any(v in low for v in ("update", "delete", "truncate", "drop", "alter")):
                out.append(("UNPARSEABLE", t))
        return out
    for st in statements:
        if st is None:
            continue
        op = None
        if isinstance(st, exp.Update):
            op = "UPDATE"
        elif isinstance(st, exp.Delete):
            op = "DELETE"
        elif isinstance(st, exp.Drop):
            op = "DROP"
        elif isinstance(st, exp.TruncateTable):
            op = "TRUNCATE"
        elif isinstance(st, exp.Alter):
            op = "ALTER"
        elif isinstance(st, exp.Insert) and st.args.get("overwrite"):
            op = "INSERT OVERWRITE"
        elif isinstance(st, exp.Command) and str(st.this).upper() in {"TRUNCATE", "ALTER"}:
            op = str(st.this).upper()
            expr = str(st.expression or "").strip().split()
            name = expr[1] if expr and expr[0].upper() == "TABLE" and len(expr) > 1 else (expr[0] if expr else "")
            out.append((op, name.strip('"').split(".")[-1].lower()))
            continue
        if op:
            for t in st.find_all(exp.Table):
                out.append((op, t.name.lower()))
                if op in {"UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "INSERT OVERWRITE"}:
                    break
    return out


class Store:
    """Thin, guarded wrapper over a DuckDB connection holding the canonical model."""

    def __init__(self, path: str | Path = ":memory:", migrate: bool = True):
        self.path = str(path)
        self._con = duckdb.connect(self.path)
        self._lock = threading.RLock()
        if migrate:
            self.migrate()

    # ------------------------------------------------------------------ schema
    def migrate(self) -> list[str]:
        with self._lock:
            self._con.execute(
                "CREATE TABLE IF NOT EXISTS _migration (name VARCHAR PRIMARY KEY, applied_at TIMESTAMP)"
            )
            applied = {r[0] for r in self._con.execute("SELECT name FROM _migration").fetchall()}
            done: list[str] = []
            for f in _migration_files():
                if f.name in applied:
                    continue
                text = f.read_text()
                if "@dialect: postgres" in text:
                    self._con.execute("INSERT INTO _migration VALUES (?, now())", [f.name])
                    continue
                for stmt in sqlglot.transpile(text, read="postgres", write="duckdb"):
                    if stmt.strip():
                        self._con.execute(stmt)
                self._con.execute("INSERT INTO _migration VALUES (?, now())", [f.name])
                done.append(f.name)
            return done

    def tables(self) -> list[str]:
        rows = self._con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1"
        ).fetchall()
        return [r[0] for r in rows]

    def columns(self, table: str) -> list[str]:
        rows = self._con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name=? ORDER BY ordinal_position",
            [table],
        ).fetchall()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------ guarded access
    def _guard(self, sql: str) -> None:
        for op, table in _mutated_tables(sql):
            if table in APPEND_ONLY:
                raise AppendOnlyViolation(f"{op} on append-only table '{table}' is not permitted")

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> None:
        self._guard(sql)
        with self._lock:
            self._con.execute(sql, list(params) if params else [])

    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        self._guard(sql)
        with self._lock:
            cur = self._con.execute(sql, list(params) if params else [])
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] | None = None) -> Any:
        rows = self.query(sql, params)
        return next(iter(rows[0].values())) if rows else None

    def insert(self, table: str, rows: Mapping[str, Any] | Iterable[Mapping[str, Any]]) -> int:
        if isinstance(rows, Mapping):
            rows = [rows]
        rows = list(rows)
        if not rows:
            return 0
        cols = sorted({k for r in rows for k in r})
        quoted = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join("?" for _ in cols)
        sql = f'INSERT INTO "{table}" ({quoted}) VALUES ({placeholders})'
        with self._lock:
            self._con.executemany(sql, [[_to_db(r.get(c)) for c in cols] for r in rows])
        return len(rows)

    def update(self, table: str, where: Mapping[str, Any], values: Mapping[str, Any]) -> None:
        if table.lower() in APPEND_ONLY:
            raise AppendOnlyViolation(f"UPDATE on append-only table '{table}' is not permitted")
        sets = ", ".join(f'"{k}" = ?' for k in values)
        conds = " AND ".join(f'"{k}" = ?' for k in where)
        with self._lock:
            self._con.execute(
                f'UPDATE "{table}" SET {sets} WHERE {conds}',
                [_to_db(v) for v in values.values()] + list(where.values()),
            )

    def get(self, table: str, **where: Any) -> dict[str, Any] | None:
        conds = " AND ".join(f'"{k}" = ?' for k in where) or "TRUE"
        rows = self.query(f'SELECT * FROM "{table}" WHERE {conds} LIMIT 1', list(where.values()))
        return rows[0] if rows else None

    def all(self, table: str, order_by: str | None = None, **where: Any) -> list[dict[str, Any]]:
        conds = " AND ".join(f'"{k}" = ?' for k in where) or "TRUE"
        order = f" ORDER BY {order_by}" if order_by else ""
        return self.query(f'SELECT * FROM "{table}" WHERE {conds}{order}', list(where.values()))

    @property
    def raw(self) -> duckdb.DuckDBPyConnection:
        """Unguarded connection — for read-only analytics only. Never mutate through it."""
        return self._con

    def close(self) -> None:
        self._con.close()


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value
