"""Harvester base: read-only catalog access → canonical rows.

Concrete harvesters (SQL Server, Oracle, Teradata) only issue read statements
through a scoped :class:`~altitude_connectors.readonly.ReadOnlyConnection`
whose scope is the source's published permission manifest. They never see the
raw driver connection.
"""

from __future__ import annotations

import fnmatch
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from altitude.core.ids import stable_id

from ..canonical import CODE_TYPES, EDGE_KINDS, OBJECT_TYPES, HarvestBundle, code_hash, count_loc, object_id, system_id
from ..manifest import Manifest, load_manifest
from ..readonly import ReadOnlyConnection, read_only
from ..sqlrefs import code_refs, normalize_name

#: The canonical ``usage_90d`` column defines this window (it is a column definition, not a tunable).
USAGE_WINDOW_DAYS = 90


def month_bounds(d: date) -> tuple[date, date]:
    start = d.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1)


def as_datetime(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    if isinstance(v, (int, float)):
        s = str(int(v))  # SQL Agent style YYYYMMDD
        return datetime(int(s[:4]), int(s[4:6]), int(s[6:8]))
    return datetime.fromisoformat(str(v).replace("Z", ""))


class ObjectIndex:
    """Resolves (possibly partial) names found in code to harvested object ids."""

    def __init__(self, default_prefix: Iterable[str] = ()):
        self.default_prefix = [p.lower() for p in default_prefix]
        self._by_full: dict[str, str] = {}
        self._by_suffix: dict[str, set[str]] = defaultdict(set)

    def add(self, fq_name: str, oid: str) -> None:
        parts = normalize_name(fq_name).split(".")
        self._by_full[".".join(parts)] = oid
        for i in range(1, len(parts)):
            self._by_suffix[".".join(parts[i:])].add(oid)

    def resolve(self, name: str) -> str | None:
        key = normalize_name(name)
        if key in self._by_full:
            return self._by_full[key]
        parts = key.split(".")
        for i in range(len(self.default_prefix)):
            cand = ".".join(self.default_prefix[i:] + parts)
            if cand in self._by_full:
                return self._by_full[cand]
            cand = ".".join(self.default_prefix[:i + 1] + parts)
            if cand in self._by_full:
                return self._by_full[cand]
        hits = self._by_suffix.get(key, set())
        if len(hits) == 1:
            return next(iter(hits))
        if hits and self.default_prefix:
            scoped = [h for h in hits if any(h == self._by_full.get(".".join(self.default_prefix[i:] + parts))
                                             for i in range(len(self.default_prefix)))]
            if len(scoped) == 1:
                return scoped[0]
        return None


@dataclass
class _Usage:
    count: int = 0
    users: set[str] = field(default_factory=set)
    users_known: bool = False


class Harvester:
    """Base class. Subclasses implement :meth:`collect`."""

    source: str = ""
    version = "1.0.0"

    def __init__(self, connection: Any, *, engagement_id: str, system_name: str, manifest: Manifest | None = None,
                 execute_dialect: str | None = None, script_dirs: Iterable[str | Path] = (),
                 as_of: datetime | None = None):
        self.manifest = manifest or load_manifest(self.source)
        if isinstance(connection, ReadOnlyConnection):
            if connection.scope is None:
                raise ValueError("harvesters require a read-only connection scoped to the permission manifest")
            self.conn = connection
        else:
            self.conn = read_only(connection, self.manifest.dialect, scope=self.manifest.scope,
                                  execute_dialect=execute_dialect)
        self.engagement_id = engagement_id
        self.system_name = system_name
        self.script_dirs = [Path(p) for p in script_dirs]
        self.as_of = (as_of or datetime.now(timezone.utc)).replace(tzinfo=None)
        self.source_system_id = system_id(engagement_id, self.source, system_name)
        self.system_version: str | None = None
        self.objects: dict[str, dict[str, Any]] = {}
        self.texts: dict[str, str] = {}
        self.columns: list[dict[str, Any]] = []
        self.edges: dict[tuple[str, str, str], str] = {}
        self.usage: dict[tuple[str, date], _Usage] = defaultdict(_Usage)
        self.last_used: dict[str, datetime] = {}
        self.grants: list[dict[str, Any]] = []
        self.attrs: dict[tuple[str, str], str] = {}
        self.index = ObjectIndex(self.default_prefix())
        self.notes: list[str] = []

    # ------------------------------------------------------------------ hooks
    def default_prefix(self) -> list[str]:
        return []

    def collect(self) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    # ------------------------------------------------------------------ helpers for subclasses
    def q(self, sql: str) -> list[dict[str, Any]]:
        return self.conn.query(sql)

    def add_object(self, fq_name: str, object_type: str, text: str | None = None, **attrs: Any) -> str:
        if object_type not in OBJECT_TYPES:
            raise ValueError(f"unknown canonical object type {object_type!r}")
        oid = object_id(self.source_system_id, fq_name)
        if oid in self.objects:
            if text and oid not in self.texts:
                self.texts[oid] = text
            return oid
        self.objects[oid] = {"object_id": oid, "fq_name": fq_name, "object_type": object_type}
        if text is not None:
            self.texts[oid] = text
        self.index.add(fq_name, oid)
        for k, v in attrs.items():
            self.set_attr(oid, k, v)
        return oid

    def set_attr(self, oid: str, attr: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True, default=str)
        elif isinstance(value, (datetime, date)):
            value = value.isoformat()
        self.attrs[(oid, attr)] = str(value)

    def add_edge(self, from_id: str | None, to_id: str | None, kind: str, evidence: str) -> None:
        if not from_id or not to_id or from_id == to_id:
            return
        if kind not in EDGE_KINDS:
            raise ValueError(f"unknown edge kind {kind!r}")
        key = (from_id, to_id, kind)
        prev = self.edges.get(key)
        self.edges[key] = evidence if prev is None or evidence < prev else prev

    def add_usage(self, oid: str | None, at: Any, count: int = 1, user: str | None = None) -> None:
        if not oid or not count:
            return
        ts = as_datetime(at)
        if ts is None or ts > self.as_of:
            return
        start, _ = month_bounds(ts.date())
        u = self.usage[(oid, start)]
        u.count += int(count)
        if user is not None:
            u.users.add(str(user).lower())
            u.users_known = True
        if oid not in self.last_used or ts > self.last_used[oid]:
            self.last_used[oid] = ts

    def add_column(self, oid: str | None, name: str, ordinal: int, data_type: str, nullable: bool | None,
                   **attributes: Any) -> None:
        if not oid:
            return
        attrs = {k: v for k, v in attributes.items() if v is not None}
        self.columns.append({"object_id": oid, "column_name": name, "ordinal": int(ordinal),
                             "data_type": data_type, "nullable": nullable, "attributes": attrs or None,
                             "sensitivity_tag": None})

    def add_grant(self, grantee: str, grantee_type: str, privilege: str, object_fq_name: str | None) -> None:
        gid = stable_id("GRT", self.source_system_id, grantee.lower(), privilege.upper(), (object_fq_name or "").lower())
        if any(g["grant_id"] == gid for g in self.grants):
            return
        self.grants.append({"grant_id": gid, "source_system_id": self.source_system_id, "grantee": grantee,
                            "grantee_type": grantee_type, "privilege": privilege.upper(),
                            "object_fq_name": object_fq_name, "mapped_to": None, "mapping_status": "unmapped"})

    def resolve(self, name: str) -> str | None:
        return self.index.resolve(name)

    def edges_from_code(self, oid: str, text: str | None, evidence: str) -> None:
        """Add reads/writes/calls edges for every resolvable reference in ``text``."""
        refs = code_refs(text)
        unresolved = []
        for kind, names in refs.by_kind().items():
            for name in sorted(names):
                target = self.resolve(name)
                if target is None:
                    unresolved.append(name)
                    continue
                if kind == "calls" and self.objects[target]["object_type"] not in CODE_TYPES:
                    kind_eff = "reads"
                elif kind == "reads" and self.objects[target]["object_type"] in {"procedure", "function", "macro"}:
                    kind_eff = "calls"
                else:
                    kind_eff = kind
                self.add_edge(oid, target, kind_eff, evidence)
        if unresolved:
            prev = json.loads(self.attrs.get((oid, "unresolved_refs"), "[]"))
            self.set_attr(oid, "unresolved_refs", sorted(set(prev) | set(unresolved)))

    def usage_from_query_text(self, text: str | None, at: Any, count: int, user: str | None = None) -> None:
        """Attribute an ad hoc query's executions to the objects it references (text is never shipped)."""
        refs = code_refs(text)
        for name in sorted(refs.all()):
            self.add_usage(self.resolve(name), at, count, user)

    def script_files(self) -> list[Path]:
        globs = self.manifest.file_globs
        files = set()
        for d in self.script_dirs:
            for p in d.rglob("*"):
                rel = p.relative_to(d).as_posix()
                if p.is_file() and any(fnmatch.fnmatch(rel, g) or fnmatch.fnmatch(p.name, g.split("/")[-1])
                                       for g in globs):
                    files.add(p)
        return sorted(files)

    # ------------------------------------------------------------------ build
    def harvest(self) -> HarvestBundle:
        self.collect()
        harvested_at = self.as_of
        window_start = self.as_of - timedelta(days=USAGE_WINDOW_DAYS)
        usage_rows = []
        recent: dict[str, int] = defaultdict(int)
        for (oid, start), u in sorted(self.usage.items()):
            _, end = month_bounds(start)
            usage_rows.append({"object_id": oid, "period_start": start, "period_end": end, "query_count": u.count,
                               "distinct_users": len(u.users) if u.users_known else None})
        # usage_90d: whole months overlapping the window are pro-rated by days in window.
        for (oid, start), u in self.usage.items():
            _, end = month_bounds(start)
            overlap_start = max(start, window_start.date())
            overlap_end = min(end, self.as_of.date())
            if overlap_end < overlap_start:
                continue
            days_in_month = (end - start).days + 1
            share = ((overlap_end - overlap_start).days + 1) / days_in_month
            recent[oid] += round(u.count * share)
        objects, versions = [], []
        for oid, o in sorted(self.objects.items()):
            text = self.texts.get(oid)
            h = code_hash(text)
            objects.append({
                "object_id": oid, "engagement_id": self.engagement_id, "source_system_id": self.source_system_id,
                "object_type": o["object_type"], "fq_name": o["fq_name"], "code_hash": h,
                "loc": count_loc(text) if text else None, "last_used_at": self.last_used.get(oid),
                "usage_90d": recent.get(oid, 0), "disposition": None, "disposition_conf": None,
                "disposition_rationale": None, "tier": None, "complexity_score": None,
                "harvested_at": harvested_at,
            })
            if text is not None:
                versions.append({"object_id": oid, "code_hash": h, "source_text": text, "harvested_at": harvested_at})
        edges = [{"from_object_id": f, "to_object_id": t, "kind": k, "evidence": e}
                 for (f, t, k), e in sorted(self.edges.items())]
        attributes = [{"object_id": oid, "attr": a, "value": v} for (oid, a), v in sorted(self.attrs.items())]
        statements = [{"seq": e.seq, "verdict": e.verdict, "reason": e.reason, "objects": ",".join(e.objects),
                       "row_count": e.rows, "statement": e.sql} for e in self.conn.log.entries]
        history_start = min((r["period_start"] for r in usage_rows), default=None)
        meta = {
            "as_of": self.as_of.isoformat(),
            "engagement_id": self.engagement_id,
            "source": self.source,
            "dialect": self.manifest.dialect,
            "system_name": self.system_name,
            "source_system_id": self.source_system_id,
            "manifest_id": self.manifest.id,
            "manifest_version": self.manifest.version,
            "harvester": f"{type(self).__module__}@{self.version}",
            "usage_history_start": history_start.isoformat() if history_start else None,
            "statements": len(self.conn.log.allowed()),
            "refused": len(self.conn.log.refused()),
            "notes": sorted(self.notes),
        }
        source_system = {
            "source_system_id": self.source_system_id, "engagement_id": self.engagement_id, "dialect": self.source,
            "name": self.system_name, "version": self.system_version,
            "permission_manifest": self.manifest.summary(),
        }
        return HarvestBundle(source_system=source_system, meta=meta, objects=objects, versions=versions,
                             columns=sorted(self.columns, key=lambda c: (c["object_id"], c["ordinal"])),
                             edges=edges, usage=usage_rows, grants=sorted(self.grants, key=lambda g: g["grant_id"]),
                             attributes=attributes, statements=statements)
