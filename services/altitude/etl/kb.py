"""Loaders for ETL / scheduler / BI knowledge (``knowledge/{etl,schedulers,bi}/*.yaml``)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from altitude.core.knowledge import load_yaml
from altitude.core.paths import knowledge_dir


@lru_cache(maxsize=32)
def _load(rel: str, root: str) -> Any:
    return load_yaml(rel, Path(root)) or {}


def load(rel: str, root: Path | None = None) -> Any:
    return _load(rel, str(root or knowledge_dir()))


def components(tool: str) -> dict:
    return load(f"etl/components_{tool}.yaml")


def component_for(tool: str, class_id: str) -> dict | None:
    """The component entry whose ``class_ids`` include ``class_id`` (case-insensitive, version suffix tolerant)."""
    cid = (class_id or "").strip()
    base = re.sub(r"\.\d+$", "", cid)
    for comp in components(tool)["components"]:
        for c in comp["class_ids"]:
            if c.lower() in {cid.lower(), base.lower()}:
                return comp
    return None


def known_issues() -> dict[str, dict]:
    out = {k["id"]: k for k in load("etl/known_issues.yaml").get("known_issues", [])}
    out.update({k["id"]: k for k in load("schedulers/known_issues.yaml").get("known_issues", [])})
    return out


def conventions() -> dict:
    return load("etl/dbt_conventions.yaml")


def scheduler_policies() -> dict:
    return load("schedulers/policies.yaml")


def command_mappings() -> list[dict]:
    return list(load("schedulers/command_mappings.yaml").get("mappings", []))


def scheduler_sources() -> dict:
    return load("schedulers/sources.yaml")


def bi_approaches() -> dict:
    return load("bi/approaches.yaml")


def map_type(tool: str, raw: str, length: Any = None, precision: Any = None, scale: Any = None) -> str:
    """Tool data type -> canonical Snowflake type using the knowledge type map."""
    types = components(tool)["data_types"]
    key = (raw or "").strip()
    tmpl = types.get(key) or types.get(key.lower())
    if tmpl is None:
        m = re.match(r"^\s*([A-Za-z_ /]+?)\s*\(\s*(\d+)\s*(?:,\s*(\d+))?\s*\)\s*$", key)
        if m:
            tmpl = types.get(m.group(1).lower())
            precision = precision or m.group(2)
            length = length or m.group(2)
            scale = scale if scale not in (None, "") else m.group(3)
    if tmpl is None:
        return "VARCHAR"
    length = _num(length) or _num(precision)
    precision = _num(precision) or _num(length)
    scale = _num(scale) or 0
    if "{length}" in tmpl and not length:
        return re.sub(r"\(\{length\}\)", "", tmpl)
    if "{precision}" in tmpl and not precision:
        return re.sub(r"\(\{precision\}(,\{scale\})?\)", "", tmpl) if "DECIMAL" not in tmpl else "DECIMAL(38,0)"
    return tmpl.format(length=length, precision=precision, scale=scale)


def _num(v: Any) -> int | None:
    try:
        n = int(str(v).strip())
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None
