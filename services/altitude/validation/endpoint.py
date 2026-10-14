"""In-boundary execution endpoints (source and Snowflake target).

An :class:`Endpoint` wraps a DB-API style connection (DuckDB in tests and local runs, a
Snowflake connector cursor in the client account). Validation SQL is authored in DuckDB SQL
and rendered for the endpoint's dialect with sqlglot (``unsupported_level=RAISE``).

Row-level reads happen only here, inside the client boundary; the control plane receives
aggregates, hashes are compared in-process, and mismatch keys go to a local file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import sqlglot
from sqlglot.errors import ErrorLevel


@dataclass
class Endpoint:
    con: Any
    dialect: str = "duckdb"
    name: str = ""

    def render(self, sql: str) -> str:
        if self.dialect == "duckdb":
            return sql
        out = sqlglot.transpile(sql, read="duckdb", write=self.dialect, unsupported_level=ErrorLevel.RAISE)
        return ";\n".join(out)

    def query(self, sql: str, params: list | None = None) -> tuple[list[str], list[tuple]]:
        cur = self.con.cursor() if hasattr(self.con, "cursor") and self.dialect != "duckdb" else self.con
        res = cur.execute(self.render(sql), params or [])
        res = res if res is not None else cur
        cols = [d[0] for d in res.description] if res.description else []
        return cols, [tuple(r) for r in res.fetchall()]

    def columns(self, table: str) -> list[tuple[str, str, bool]]:
        """[(column_name, data_type, nullable)] in ordinal order."""
        parts = [p.strip('"') for p in table.split(".")]
        name = parts[-1]
        sql = ("SELECT column_name, data_type, is_nullable FROM information_schema.columns "
               "WHERE lower(table_name) = lower(?)")
        params: list = [name]
        if len(parts) > 1:
            sql += " AND lower(table_schema) = lower(?)"
            params.append(parts[-2])
        sql += " ORDER BY ordinal_position"
        _, rows = self.query(sql, params)
        return [(r[0], str(r[1]), str(r[2]).upper() in ("YES", "TRUE", "Y")) for r in rows]
