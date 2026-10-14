"""Canonical estate model produced by every harvester (Section 30, "Estate" group).

A :class:`HarvestBundle` holds rows for ``source_system``, ``source_object``,
``object_version``, ``column``, ``dependency_edge``, ``usage_stat``, ``grant``
and ``object_attribute`` plus the statement log. It is what the extraction
agent ships out of the client boundary: metadata, code and usage aggregates
only. It can be written to the control-plane :class:`~altitude.core.store.Store`
or sealed into a harvest :class:`~altitude.core.snapshot.Snapshot`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from altitude.core.ids import canonical_json, content_hash, stable_id
from altitude.core.snapshot import Snapshot, SnapshotWriter

#: Snapshot layout of the canonical estate tables (DuckDB types; JSON stored as text).
CANONICAL_TABLES: dict[str, dict[str, str]] = {
    "source_system": {
        "source_system_id": "VARCHAR", "engagement_id": "VARCHAR", "dialect": "VARCHAR", "name": "VARCHAR",
        "version": "VARCHAR", "permission_manifest": "VARCHAR",
    },
    "source_object": {
        "object_id": "VARCHAR", "engagement_id": "VARCHAR", "source_system_id": "VARCHAR",
        "object_type": "VARCHAR", "fq_name": "VARCHAR", "code_hash": "VARCHAR", "loc": "INTEGER",
        "last_used_at": "TIMESTAMP", "usage_90d": "INTEGER", "disposition": "VARCHAR",
        "disposition_conf": "DECIMAL(4,3)", "disposition_rationale": "VARCHAR", "tier": "VARCHAR",
        "complexity_score": "DECIMAL(5,2)", "harvested_at": "TIMESTAMP",
    },
    "object_version": {
        "object_id": "VARCHAR", "code_hash": "VARCHAR", "source_text": "VARCHAR", "harvested_at": "TIMESTAMP",
    },
    "column": {
        "object_id": "VARCHAR", "column_name": "VARCHAR", "ordinal": "INTEGER", "data_type": "VARCHAR",
        "nullable": "BOOLEAN", "attributes": "VARCHAR", "sensitivity_tag": "VARCHAR",
    },
    "dependency_edge": {
        "from_object_id": "VARCHAR", "to_object_id": "VARCHAR", "kind": "VARCHAR", "evidence": "VARCHAR",
    },
    "usage_stat": {
        "object_id": "VARCHAR", "period_start": "DATE", "period_end": "DATE", "query_count": "INTEGER",
        "distinct_users": "INTEGER",
    },
    "grant": {
        "grant_id": "VARCHAR", "source_system_id": "VARCHAR", "grantee": "VARCHAR", "grantee_type": "VARCHAR",
        "privilege": "VARCHAR", "object_fq_name": "VARCHAR", "mapped_to": "VARCHAR", "mapping_status": "VARCHAR",
    },
    "object_attribute": {"object_id": "VARCHAR", "attr": "VARCHAR", "value": "VARCHAR"},
    "harvest_statement": {
        "seq": "INTEGER", "verdict": "VARCHAR", "reason": "VARCHAR", "objects": "VARCHAR", "row_count": "INTEGER",
        "statement": "VARCHAR",
    },
}

#: Object types whose source text is code (shipped as metadata, never data).
CODE_TYPES = frozenset({"view", "procedure", "function", "package", "trigger", "macro", "script", "etl_job",
                        "schedule"})
OBJECT_TYPES = CODE_TYPES | {"table", "report"}
EDGE_KINDS = frozenset({"reads", "writes", "calls", "schedules"})

_ROW_KEY = {
    "source_object": ("object_id",),
    "object_version": ("object_id", "code_hash"),
    "column": ("object_id", "ordinal"),
    "dependency_edge": ("from_object_id", "to_object_id", "kind"),
    "usage_stat": ("object_id", "period_start"),
    "grant": ("grant_id",),
    "object_attribute": ("object_id", "attr"),
    "harvest_statement": ("seq",),
}


def system_id(engagement_id: str, dialect: str, name: str) -> str:
    return stable_id("SRC", engagement_id, dialect, name.lower())


def object_id(source_system_id: str, fq_name: str) -> str:
    return stable_id("OBJ", source_system_id, fq_name.lower(), length=10)


def code_hash(text: str | None) -> str | None:
    if text is None:
        return None
    return content_hash("\n".join(line.rstrip() for line in text.strip().splitlines()), 16)


def count_loc(text: str | None) -> int:
    """Non-blank lines that are not pure comment lines."""
    if not text:
        return 0
    n = 0
    in_block = False
    for raw in text.splitlines():
        line = raw.strip()
        if in_block:
            if "*/" in line:
                in_block = False
                line = line.split("*/", 1)[1].strip()
            else:
                continue
        if line.startswith("/*") and "*/" not in line:
            in_block = True
            continue
        if not line or line.startswith("--") or (line.startswith("/*") and line.endswith("*/")):
            continue
        n += 1
    return n


def _sort_key(table: str, row: dict[str, Any]) -> tuple:
    return tuple(str(row.get(k)) for k in _ROW_KEY.get(table, tuple(sorted(row))))


@dataclass
class HarvestBundle:
    """Canonical rows produced by one harvest of one source system."""

    source_system: dict[str, Any]
    meta: dict[str, Any]
    objects: list[dict[str, Any]] = field(default_factory=list)
    versions: list[dict[str, Any]] = field(default_factory=list)
    columns: list[dict[str, Any]] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    usage: list[dict[str, Any]] = field(default_factory=list)
    grants: list[dict[str, Any]] = field(default_factory=list)
    attributes: list[dict[str, Any]] = field(default_factory=list)
    statements: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ views
    def tables(self) -> dict[str, list[dict[str, Any]]]:
        raw = {
            "source_system": [self.source_system],
            "source_object": self.objects,
            "object_version": self.versions,
            "column": self.columns,
            "dependency_edge": self.edges,
            "usage_stat": self.usage,
            "grant": self.grants,
            "object_attribute": self.attributes,
            "harvest_statement": self.statements,
        }
        return {t: sorted(rows, key=lambda r, t=t: _sort_key(t, r)) for t, rows in raw.items()}

    def object_by_name(self, fq_name: str) -> dict[str, Any] | None:
        low = fq_name.lower()
        return next((o for o in self.objects if o["fq_name"].lower() == low), None)

    def counts(self) -> dict[str, int]:
        return {t: len(rows) for t, rows in self.tables().items()}

    # ------------------------------------------------------------------ serialisation
    def to_json(self) -> str:
        return json.dumps({"meta": self.meta, "tables": self.tables()}, sort_keys=True, default=_json_default,
                          indent=1)

    def content_hash(self) -> str:
        tables = {k: v for k, v in self.tables().items() if k != "harvest_statement"}
        return content_hash(tables, 32)

    # ------------------------------------------------------------------ sinks
    def to_snapshot(self, directory: str | Path, snapshot_id: str | None = None) -> Snapshot:
        snapshot_id = snapshot_id or stable_id("HRV", self.source_system["source_system_id"], self.content_hash())
        meta = dict(self.meta)
        meta.setdefault("engagement_id", self.source_system["engagement_id"])
        w = SnapshotWriter(directory, snapshot_id, kind="harvest", metadata=meta)
        for name, rows in self.tables().items():
            cols = CANONICAL_TABLES[name]
            w.add_table_from_rows(name, [_snapshot_row(r, cols) for r in rows], cols)
        sealed_at = meta.get("as_of")
        return w.seal(sealed_at=datetime.fromisoformat(sealed_at) if isinstance(sealed_at, str) else None)

    def to_store(self, store: Any) -> dict[str, int]:
        """Upsert the estate rows into the control-plane store (replacing a previous harvest of this system)."""
        sid = self.source_system["source_system_id"]
        ids = [o["object_id"] for o in self.objects]
        store.execute('DELETE FROM source_system WHERE source_system_id = ?', [sid])
        store.execute('DELETE FROM "grant" WHERE source_system_id = ?', [sid])
        if ids:
            marks = ", ".join("?" for _ in ids)
            for table, col in (("object_version", "object_id"), ("column", "object_id"),
                               ("usage_stat", "object_id"), ("object_attribute", "object_id"),
                               ("dependency_edge", "from_object_id"), ("source_object", "object_id")):
                store.execute(f'DELETE FROM "{table}" WHERE "{col}" IN ({marks})', ids)
        out = {}
        for name, rows in self.tables().items():
            if name == "harvest_statement":
                continue
            prepared = []
            for r in rows:
                r = dict(r)
                if name == "source_system" and isinstance(r.get("permission_manifest"), str):
                    r["permission_manifest"] = json.loads(r["permission_manifest"])
                if name == "column" and isinstance(r.get("attributes"), str):
                    r["attributes"] = json.loads(r["attributes"])
                prepared.append(r)
            out[name] = store.insert(name, prepared)
        return out


def _json_default(v: Any) -> Any:
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    raise TypeError(type(v))


def _snapshot_row(row: dict[str, Any], cols: dict[str, str]) -> dict[str, Any]:
    out = {}
    for c in cols:
        v = row.get(c)
        if isinstance(v, (dict, list)):
            v = canonical_json(v)
        out[c] = v
    return out
