"""Deterministic synthetic source data for the dbt harness.

Rows are a pure function of (table, column, row index): primary keys are dense and unique, foreign keys
point at existing parent keys, columns compared with literals in the mapping logic draw from those literals
(plus one value outside them), strings carry padding / mixed case so TRIM / UPPER logic is exercised,
nullable non-key columns get periodic NULLs, and numbers respect their DECIMAL precision.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

import duckdb
import sqlglot

from altitude.core.rubric import RubricSet, default_rubrics

from .graph import Column

_BASE_DATE = date(2025, 1, 1)  # fixed: synthetic data must be reproducible
_STRIDE = 7          # threshold-ok: co-prime stride spreading foreign keys over parents
_NULL_EVERY = 13     # threshold-ok: period of NULLs in nullable columns
_PAD_EVERY = 5       # threshold-ok: period of padded/mixed-case strings


def _precision(t: str) -> tuple[int | None, int | None]:
    m = re.search(r"\((\d+)\s*(?:,\s*(\d+))?\)", t)
    return (int(m.group(1)), int(m.group(2) or 0)) if m else (None, None)


def _is_int(t: str) -> bool:
    t = t.upper()
    if t.startswith(("INTEGER", "BIGINT", "SMALLINT", "INT")):
        return True
    if t.startswith(("DECIMAL", "NUMBER", "NUMERIC")):
        return (_precision(t)[1] or 0) == 0
    return False


def key_value(table: str, col: Column, i: int) -> Any:
    if _is_int(col.type):
        return i + 1
    return f"{table[:3].upper()}{i + 1:05d}"


def value(table: str, col: Column, i: int, rows: int, domains: dict[str, list[str]],
          parents: dict[tuple[str, str], tuple[Column, int]]) -> Any:
    t = col.type.upper()
    if col.key == "primary":
        return key_value(table, col, i)
    if col.key == "foreign":
        parent = parents.get((col.ref_table or "", col.ref_column or ""))
        n_parent = parent[1] if parent else rows
        j = (i * _STRIDE + 3) % n_parent
        return key_value(col.ref_table or table, parent[0] if parent else col, j)
    if col.nullable and i % _NULL_EVERY == _NULL_EVERY - 1:
        return None
    if col.name in domains and domains[col.name]:
        vals = list(domains[col.name]) + ["OTHER"]
        v = vals[i % len(vals)]
        length = _precision(t)[0] if t.startswith(("VARCHAR", "CHAR")) else None
        return v[:length] if length else v
    if t.startswith("BOOLEAN"):
        return i % 3 == 0
    if t.startswith(("DATE",)):
        return _BASE_DATE + timedelta(days=(i * 3) % 400)
    if t.startswith(("TIMESTAMP",)):
        return datetime.combine(_BASE_DATE, datetime.min.time()) + timedelta(days=(i * 3) % 400, hours=i % 24)
    if t.startswith("TIME"):
        return f"{i % 24:02d}:{(i * 7) % 60:02d}:00"
    if _is_int(t):
        p, _ = _precision(t)
        span = 10 ** min(p or 3, 3)
        return (i * 37) % span - (span // 20 if "QUANT" in col.name.upper() else 0)
    if t.startswith(("DECIMAL", "NUMBER", "NUMERIC")):
        p, s = _precision(t)
        cap = 10 ** ((p or 12) - (s or 0)) - 1
        return round(((i * 7919) % 150000) / 100.0 % max(cap, 1), s or 0)
    if t.startswith(("DOUBLE", "FLOAT", "REAL")):
        return ((i * 13) % 1000) / 10.0
    if t.startswith("BINARY"):
        return bytes([i % 256])
    length = _precision(t)[0]
    s = f"  {col.name.title()} {i + 1} " if i % _PAD_EVERY == 0 else f"{col.name}_{i + 1}"
    return s[:length] if length else s


def generate_rows(sources: dict[tuple[str, str], Any], domains: dict[str, list[str]],
                  rows: int) -> dict[tuple[str, str], list[tuple]]:
    parents = {}
    for (system, table), st in sources.items():
        for c in st.columns.values():
            if c.key == "primary":
                parents[(table, c.name)] = (c, rows)
    data = {}
    for (system, table), st in sorted(sources.items()):
        cols = list(st.columns.values())
        data[(system, table)] = [tuple(value(table, c, i, rows, domains, parents) for c in cols) for i in range(rows)]
    return data


def duckdb_type(snowflake_type: str) -> str:
    sql = sqlglot.transpile(f"CREATE TABLE t (c {snowflake_type})", read="snowflake", write="duckdb")[0]
    return re.search(r"\(c (.*)\)$", sql).group(1)


def load(con: duckdb.DuckDBPyConnection, sources: dict[tuple[str, str], Any], domains: dict[str, list[str]],
         rubrics: RubricSet | None = None, rows: int | None = None) -> dict[tuple[str, str], int]:
    """Create every source table in DuckDB (schema = system) and fill it with synthetic rows."""
    rubrics = rubrics or default_rubrics()
    rows = rows or int(rubrics.get("rubric.etl.synthetic.rows_per_table"))
    data = generate_rows(sources, domains, rows)
    counts = {}
    for (system, table), st in sorted(sources.items()):
        cols = list(st.columns.values())
        con.execute(f'CREATE SCHEMA IF NOT EXISTS "{system}"')
        ddl = ", ".join(f'"{c.name}" {duckdb_type(c.type)}' for c in cols)
        con.execute(f'CREATE OR REPLACE TABLE "{system}"."{table}" ({ddl})')
        con.executemany(f'INSERT INTO "{system}"."{table}" VALUES ({", ".join("?" for _ in cols)})',
                        [list(r) for r in data[(system, table)]])
        counts[(system, table)] = len(data[(system, table)])
    return counts
