"""Read-only view of a sealed harvest snapshot (the assessment's only input)."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property
from typing import Any

from altitude.core.snapshot import Snapshot

CODE_TYPES = frozenset({"view", "procedure", "function", "package", "trigger", "macro", "script", "etl_job", "schedule"})
CONSUMER_KINDS = frozenset({"reads", "calls", "schedules"})


@dataclass
class EstateObject:
    object_id: str
    fq_name: str
    object_type: str
    loc: int
    usage_90d: int
    last_used_at: datetime | None
    text: str | None
    attrs: dict[str, str] = field(default_factory=dict)
    columns: list[dict[str, Any]] = field(default_factory=list)

    @property
    def is_code(self) -> bool:
        return self.object_type in CODE_TYPES

    def attr_int(self, name: str) -> int | None:
        v = self.attrs.get(name)
        try:
            return int(v) if v is not None else None
        except ValueError:
            return None


class Estate:
    """Objects, lineage and usage of one harvested source system."""

    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        meta = snapshot.metadata
        self.dialect = meta.get("source") or snapshot.scalar("SELECT dialect FROM source_system LIMIT 1")
        self.as_of = datetime.fromisoformat(meta["as_of"]) if meta.get("as_of") else snapshot.scalar(
            "SELECT max(harvested_at) FROM source_object")
        hist = meta.get("usage_history_start")
        self.usage_history_start = date.fromisoformat(hist) if hist else None
        self.engagement_id = meta.get("engagement_id")
        texts = {r["object_id"]: r["source_text"] for r in snapshot.query(
            "SELECT object_id, source_text FROM object_version ORDER BY object_id, code_hash")}
        attrs: dict[str, dict[str, str]] = defaultdict(dict)
        for r in snapshot.query("SELECT object_id, attr, value FROM object_attribute ORDER BY object_id, attr"):
            attrs[r["object_id"]][r["attr"]] = r["value"]
        cols: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in snapshot.query('SELECT object_id, column_name, ordinal, data_type, attributes FROM "column" '
                                "ORDER BY object_id, ordinal"):
            r["attributes"] = json.loads(r["attributes"]) if r["attributes"] else {}
            cols[r["object_id"]].append(r)
        self.objects: dict[str, EstateObject] = {}
        for r in snapshot.query("SELECT object_id, fq_name, object_type, loc, usage_90d, last_used_at "
                                "FROM source_object ORDER BY object_id"):
            oid = r["object_id"]
            self.objects[oid] = EstateObject(oid, r["fq_name"], r["object_type"], int(r["loc"] or 0),
                                             int(r["usage_90d"] or 0), r["last_used_at"], texts.get(oid),
                                             attrs.get(oid, {}), cols.get(oid, []))
        self.edges = [(r["from_object_id"], r["to_object_id"], r["kind"]) for r in snapshot.query(
            "SELECT from_object_id, to_object_id, kind FROM dependency_edge ORDER BY 1, 2, 3")
            if r["from_object_id"] in self.objects and r["to_object_id"] in self.objects]

    # ------------------------------------------------------------------ graph helpers
    @cached_property
    def outbound(self) -> dict[str, list[tuple[str, str]]]:
        out: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for f, t, k in self.edges:
            out[f].append((t, k))
        return out

    @cached_property
    def inbound(self) -> dict[str, list[tuple[str, str]]]:
        inc: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for f, t, k in self.edges:
            inc[t].append((f, k))
        return inc

    def consumers(self, oid: str) -> list[str]:
        return sorted({f for f, k in self.inbound.get(oid, []) if k in CONSUMER_KINDS})

    def writers(self, oid: str) -> list[str]:
        return sorted({f for f, k in self.inbound.get(oid, []) if k == "writes"})

    def reads(self, oid: str) -> list[str]:
        return sorted({t for t, k in self.outbound.get(oid, []) if k in CONSUMER_KINDS})

    def writes(self, oid: str) -> list[str]:
        return sorted({t for t, k in self.outbound.get(oid, []) if k == "writes"})

    @property
    def history_days(self) -> int | None:
        if self.usage_history_start is None or self.as_of is None:
            return None
        return (self.as_of.date() - self.usage_history_start).days

    def view_depth(self, oid: str, _seen: frozenset = frozenset()) -> int:
        """Number of stacked view layers from ``oid`` down to base objects (a view on tables = 1)."""
        o = self.objects[oid]
        if o.object_type != "view" or oid in _seen:
            return 0
        below = [self.view_depth(t, _seen | {oid}) for t, k in self.outbound.get(oid, []) if k == "reads"]
        return 1 + max(below, default=0)

    def name(self, oid: str) -> str:
        return self.objects[oid].fq_name
