"""Extraction agent (Section 29.2).

Runs inside the client network, connects read-only to a source, harvests
metadata, code and usage, and ships only the canonical bundle. Before anything
leaves the boundary :func:`assert_metadata_only` re-checks the bundle:

- only canonical tables and columns (no free-form payloads);
- source text only for code objects (views, procedures, scripts, jobs, ...);
- every statement executed was an allowed read within the permission manifest's
  ``objects_read`` (so no user table was ever read) and none was refused.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from altitude.core.errors import ReadOnlyViolation
from altitude.core.ids import stable_id
from altitude.core.snapshot import Snapshot

from .canonical import CANONICAL_TABLES, CODE_TYPES, HarvestBundle
from .harvest import harvester_for
from .manifest import Manifest, load_manifest
from .readonly import check_scope


class EgressViolation(ReadOnlyViolation):
    """A harvest bundle contained something other than metadata, code and usage aggregates."""


def assert_metadata_only(bundle: HarvestBundle, manifest: Manifest) -> None:
    tables = bundle.tables()
    unknown = set(tables) - set(CANONICAL_TABLES)
    if unknown:
        raise EgressViolation(f"non-canonical tables in bundle: {sorted(unknown)}")
    for name, rows in tables.items():
        allowed = set(CANONICAL_TABLES[name])
        for r in rows:
            extra = set(r) - allowed
            if extra:
                raise EgressViolation(f"{name}: non-canonical columns {sorted(extra)}")
    types = {o["object_id"]: o["object_type"] for o in bundle.objects}
    for v in bundle.versions:
        if types.get(v["object_id"]) not in CODE_TYPES:
            raise EgressViolation(f"source text shipped for non-code object {v['object_id']} ({types.get(v['object_id'])})")
    for s in bundle.statements:
        if s["verdict"] != "allowed":
            raise EgressViolation(f"harvest attempted a refused statement (#{s['seq']}): {s['reason']}")
        objs = [o for o in (s["objects"] or "").split(",") if o]
        try:
            check_scope(objs, manifest.scope)
        except ReadOnlyViolation as e:
            raise EgressViolation(str(e)) from None


class ExtractionAgent:
    """Harvest one source system and ship the metadata bundle (to a snapshot and/or the store)."""

    def __init__(self, source: str, connection: Any, *, engagement_id: str, system_name: str,
                 script_dirs: Iterable[str | Path] = (), execute_dialect: str | None = None,
                 as_of: datetime | None = None, manifest: Manifest | None = None):
        self.source = source.lower()
        self.manifest = manifest or load_manifest(self.source)
        self.harvester = harvester_for(self.source)(
            connection, engagement_id=engagement_id, system_name=system_name, manifest=self.manifest,
            execute_dialect=execute_dialect, script_dirs=script_dirs, as_of=as_of)
        self.bundle: HarvestBundle | None = None

    @property
    def statement_log(self):
        return self.harvester.conn.log

    def harvest(self) -> HarvestBundle:
        bundle = self.harvester.harvest()
        assert_metadata_only(bundle, self.manifest)
        self.bundle = bundle
        return bundle

    def ship(self, *, snapshot_dir: str | Path | None = None, store: Any = None,
             snapshot_id: str | None = None) -> Snapshot | None:
        bundle = self.bundle or self.harvest()
        assert_metadata_only(bundle, self.manifest)
        snap = bundle.to_snapshot(snapshot_dir, snapshot_id) if snapshot_dir is not None else None
        if store is not None:
            bundle.to_store(store)
            if snap is not None:
                snap.register(store)
            m = bundle.meta
            hid = stable_id("HRV", m["source_system_id"], m["as_of"], bundle.content_hash())
            if not store.get("harvest_run", harvest_id=hid):
                store.insert("harvest_run", {
                    "harvest_id": hid, "engagement_id": m["engagement_id"], "source_system_id": m["source_system_id"],
                    "dialect": m["dialect"], "manifest_id": m["manifest_id"], "manifest_version": m["manifest_version"],
                    "as_of": m["as_of"], "statements": m["statements"], "refused": m["refused"],
                    "object_count": len(bundle.objects), "snapshot_id": snap.snapshot_id if snap else None,
                    "summary": bundle.counts(),
                })
        return snap
