"""Build the CURATED layer (conformed facts and dimensions) from ``knowledge/observability/curated.yaml``."""

from __future__ import annotations

import re

import sqlglot

from altitude.core.rubric import RubricSet, default_rubrics
from altitude.synthetic.schema import HARVEST_SCHEMA

from .config import load_curated, load_sources
from .db import ObsDatabase

_RUBRIC_TOKEN = re.compile(r"\$\{(rubric\.[A-Za-z0-9_.]+)\}")


def substitute_rubric(sql: str, rubrics: RubricSet | None = None) -> str:
    """Replace ``${rubric.obs.x}`` placeholders in knowledge SQL with rubric values (numbers only)."""
    rubrics = rubrics or default_rubrics()

    def sub(m: re.Match) -> str:
        v = rubrics.get(m.group(1))
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"rubric placeholder {m.group(1)} must resolve to a number, got {v!r}")
        return repr(v)

    return _RUBRIC_TOKEN.sub(sub, sql)


def rubric_placeholders(sql: str) -> list[str]:
    return _RUBRIC_TOKEN.findall(sql or "")


def snapshot_view_sql(table: str) -> str:
    cols = ["ACCOUNT_NAME"] + [c for c in HARVEST_SCHEMA[table]["columns"] if c != "ACCOUNT_NAME"]
    select = ", ".join(f"r.{c}" for c in cols)
    return (
        f"SELECT h.SNAPSHOT_DATE, h.IS_LATEST, {select} "
        f"FROM CURATED.SNAPSHOT_HARVEST h "
        f"JOIN RAW.SNAPSHOT_MEMBERSHIP m ON m.ACCOUNT_NAME = h.ACCOUNT_NAME AND m.SOURCE_TABLE = h.SOURCE_TABLE "
        f"AND m.HARVEST_ID = h.HARVEST_ID "
        f"JOIN RAW.{table} r ON r.ACCOUNT_NAME = m.ACCOUNT_NAME AND r._ROW_HASH = m.ROW_HASH "
        f"WHERE h.SOURCE_TABLE = '{table}'"
    )


def curated_objects() -> list[tuple[str, str, str | None, dict]]:
    """``(name, duckdb_sql, snowflake_sql_or_None, definition)`` in creation order (snapshot views included)."""
    objs = load_curated()
    out: list[tuple[str, str, str | None, dict]] = []
    helper = [o for o in objs if o.get("kind") == "helper"]
    rest = [o for o in objs if o.get("kind") != "helper"]
    for o in helper:
        out.append((o["name"], o["sql"], o.get("sql_snowflake"), o))
    for cfg in load_sources():
        if cfg.is_snapshot:
            out.append((f"SNAP_{cfg.table}", snapshot_view_sql(cfg.table), None,
                        {"name": f"SNAP_{cfg.table}", "kind": "snapshot",
                         "description": f"Daily snapshots of {cfg.table} reconstructed from RAW membership."}))
    for o in rest:
        out.append((o["name"], o["sql"], o.get("sql_snowflake"), o))
    return out


def to_snowflake(sql: str) -> str:
    return sqlglot.transpile(sql, read="duckdb", write="snowflake", pretty=True)[0]


def build_curated(db: ObsDatabase, materialize: bool = True) -> list[str]:
    """(Re)create every CURATED object, in dependency order. Returns the names created.

    Locally the objects are materialised as tables (one refresh per KPI run, like dynamic tables in Snowflake);
    ``materialize=False`` creates plain views instead.
    """
    names = []
    for name, sql, _, _ in curated_objects():
        if materialize:
            db.replace_table("CURATED", name, sql)
        else:
            db.replace_view("CURATED", name, sql)
        names.append(name)
    return names
