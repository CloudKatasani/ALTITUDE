"""Shared helpers for the module skill adapters (``impl_*.py``)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from altitude.core.store import json_safe

from .registry import SkillError


def resolve_snapshot_path(ctx: Any, ref: str) -> Path:
    """A snapshot id registered in the control-plane ``snapshot`` table, or a path to a sealed ``.duckdb``."""
    row = ctx.store.get("snapshot", snapshot_id=ref)
    if row is not None:
        return Path(row["location"])
    path = Path(ref)
    if path.suffix == ".duckdb" and path.exists():
        return path
    raise SkillError(f"unknown snapshot {ref!r}: not registered in the store and not a sealed .duckdb path")


def open_snapshot(ctx: Any, ref: str, verify: bool = True):
    """Open (and register) a sealed snapshot by id or path."""
    from altitude.core.snapshot import Snapshot

    try:
        snap = Snapshot.open(resolve_snapshot_path(ctx, ref), verify=verify)
    except FileNotFoundError as e:
        raise SkillError(str(e)) from None
    snap.register(ctx.store)
    return snap


def out_dir(ctx: Any, skill: str, *parts: str) -> Path:
    """``<workspace>/<skill>/<parts...>`` (created)."""
    p = Path(ctx.workspace) / skill
    for part in parts:
        p = p / part
    p.mkdir(parents=True, exist_ok=True)
    return p


def paths(mapping: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in sorted(mapping.items())}


def safe(value: Any) -> Any:
    return json_safe(value)
