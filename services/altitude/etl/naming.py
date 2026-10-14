"""Identifier normalisation for generated SQL / dbt (lower snake case, reserved words suffixed)."""

from __future__ import annotations

import re
from functools import lru_cache

from . import kb


@lru_cache(maxsize=1)
def _reserved() -> frozenset[str]:
    return frozenset(w.lower() for w in kb.conventions().get("reserved_words", []))


def ident(name: str) -> str:
    """``Customer Name`` -> ``customer_name``; ``ORDER`` -> ``order_``; ``1st`` -> ``c_1st``."""
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", (name or "").strip()) if re.search(r"[a-z][A-Z]", name or "") else (name or "")
    s = re.sub(r"[^0-9A-Za-z]+", "_", s.strip()).strip("_").lower()
    s = re.sub(r"_+", "_", s) or "col"
    if s[0].isdigit():
        s = "c_" + s
    if s in _reserved():
        s += "_"
    return s


def table_name(name: str) -> str:
    """Strip schema/brackets: ``[dbo].[Customer]`` / ``SALES.CUSTOMERS`` -> ``customer`` / ``customers``."""
    last = re.split(r"\.", (name or "").replace("[", "").replace("]", "").replace('"', ""))[-1]
    return ident(last)


DEFAULT_SCHEMAS = {"dbo", "public", ""}


def qualified_table(name: str) -> str:
    """Like :func:`table_name` but keeps a non-default schema: ``[archive].[Orders]`` -> ``archive_orders``."""
    parts = [p for p in re.split(r"\.", (name or "").replace("[", "").replace("]", "").replace('"', "")) if p]
    if len(parts) >= 2 and parts[-2].lower() not in DEFAULT_SCHEMAS:  # threshold-ok: schema.table arity
        return ident(f"{parts[-2]}_{parts[-1]}")
    return ident(parts[-1]) if parts else "table"


def singular(name: str) -> str:
    n = name.lower()
    if n.endswith("ies") and len(n) > 3:  # threshold-ok: suffix length
        return n[:-3] + "y"
    if n.endswith("ses") or n.endswith("xes"):
        return n[:-2]
    if n.endswith("s") and not n.endswith("ss"):
        return n[:-1]
    return n
