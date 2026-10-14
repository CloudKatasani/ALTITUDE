"""Immutable, content-addressed snapshots (principle 5).

A snapshot is a DuckDB file holding harvested evidence tables plus a sealed
manifest (``<id>.manifest.json``) with a per-table content hash. Once sealed:

- the file is opened read-only and chmod'ed 0444;
- every consumer can verify it against the manifest (``Snapshot.verify``);
- any computation over it (scores, values, estimates) is reproducible because
  inputs never change and outputs carry ``snapshot_id`` + ``rubric_version``.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import duckdb

from .errors import AppendOnlyViolation
from .ids import content_hash


def _table_hash(con: duckdb.DuckDBPyConnection, table: str) -> tuple[str, int]:
    row = con.execute(
        f'SELECT md5(coalesce(string_agg(h, \'\' ORDER BY h), \'\')), count(*) '
        f'FROM (SELECT md5(CAST(t AS VARCHAR)) h FROM "{table}" t)'
    ).fetchone()
    return row[0], int(row[1])


def _user_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' AND table_name NOT LIKE '\\_%' ESCAPE '\\' ORDER BY 1"
    ).fetchall()
    return [r[0] for r in rows]


class SnapshotWriter:
    """Builds a snapshot. Tables may be added until :meth:`seal` is called."""

    def __init__(self, directory: str | Path, snapshot_id: str, kind: str, metadata: Mapping[str, Any] | None = None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.snapshot_id = snapshot_id
        self.kind = kind
        self.metadata = dict(metadata or {})
        self.path = self.directory / f"{snapshot_id}.duckdb"
        if self.path.exists() or self.manifest_path.exists():
            raise AppendOnlyViolation(f"snapshot {snapshot_id} already exists and is immutable")
        self.con = duckdb.connect(str(self.path))
        self._sealed = False

    @property
    def manifest_path(self) -> Path:
        return self.directory / f"{self.snapshot_id}.manifest.json"

    def add_table_from_rows(self, name: str, rows: Iterable[Mapping[str, Any]], columns: Mapping[str, str]) -> None:
        """Create table ``name`` with ``columns`` ({col: duckdb_type}) and insert ``rows``."""
        self._check_open()
        import pyarrow as pa

        cols = ", ".join(f'"{c}" {t}' for c, t in columns.items())
        self.con.execute(f'CREATE TABLE "{name}" ({cols})')
        names = list(columns)
        rows = list(rows)
        if rows:
            arrow_tbl = pa.table({c: [r.get(c) for r in rows] for c in names})  # noqa: F841 - DuckDB scan
            select = ", ".join(f'CAST("{c}" AS {t}) AS "{c}"' for c, t in columns.items())
            self.con.execute(f'INSERT INTO "{name}" SELECT {select} FROM arrow_tbl')

    def add_table_from_query(self, name: str, source_con: duckdb.DuckDBPyConnection, sql: str) -> None:
        self._check_open()
        df = source_con.execute(sql).arrow()  # noqa: F841 - referenced by DuckDB replacement scan
        self.con.execute(f'CREATE TABLE "{name}" AS SELECT * FROM df')

    def execute(self, sql: str, params: list | None = None) -> None:
        self._check_open()
        self.con.execute(sql, params or [])

    def _check_open(self) -> None:
        if self._sealed:
            raise AppendOnlyViolation(f"snapshot {self.snapshot_id} is sealed")

    def seal(self, sealed_at: datetime | None = None) -> "Snapshot":
        self._check_open()
        tables = {}
        for t in _user_tables(self.con):
            h, n = _table_hash(self.con, t)
            tables[t] = {"hash": h, "rows": n}
        manifest = {
            "snapshot_id": self.snapshot_id,
            "kind": self.kind,
            "metadata": self.metadata,
            "tables": tables,
            "content_hash": content_hash(tables, 32),
            "sealed_at": (sealed_at or datetime.now(timezone.utc)).isoformat(),
        }
        self.con.execute("CHECKPOINT")
        self.con.close()
        self._sealed = True
        self.manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
        for p in (self.path, self.manifest_path):
            os.chmod(p, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        return Snapshot.open(self.path)


@dataclass
class Snapshot:
    path: Path
    manifest: dict
    con: duckdb.DuckDBPyConnection

    @classmethod
    def open(cls, path: str | Path, verify: bool = False) -> "Snapshot":
        path = Path(path)
        manifest_path = path.with_name(path.name.replace(".duckdb", ".manifest.json"))
        if not manifest_path.exists():
            raise FileNotFoundError(f"snapshot {path} is not sealed (no manifest)")
        manifest = json.loads(manifest_path.read_text())
        con = duckdb.connect(str(path), read_only=True)
        snap = cls(path, manifest, con)
        if verify:
            snap.verify()
        return snap

    @property
    def snapshot_id(self) -> str:
        return self.manifest["snapshot_id"]

    @property
    def content_hash(self) -> str:
        return self.manifest["content_hash"]

    @property
    def metadata(self) -> dict:
        return self.manifest.get("metadata", {})

    def tables(self) -> list[str]:
        return sorted(self.manifest["tables"])

    def has_table(self, name: str) -> bool:
        return name in self.manifest["tables"]

    def verify(self) -> None:
        for t, info in self.manifest["tables"].items():
            h, n = _table_hash(self.con, t)
            if h != info["hash"] or n != info["rows"]:
                raise AppendOnlyViolation(f"snapshot {self.snapshot_id}: table {t} does not match its sealed hash")
        if set(_user_tables(self.con)) != set(self.manifest["tables"]):
            raise AppendOnlyViolation(f"snapshot {self.snapshot_id}: table set differs from manifest")

    def query(self, sql: str, params: list | None = None) -> list[dict[str, Any]]:
        cur = self.con.execute(sql, params or [])
        cols = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def scalar(self, sql: str, params: list | None = None) -> Any:
        row = self.con.execute(sql, params or []).fetchone()
        return row[0] if row else None

    def register(self, store) -> None:
        """Record this snapshot in the control-plane ``snapshot`` table (append-only)."""
        if store.get("snapshot", snapshot_id=self.snapshot_id):
            return
        store.insert(
            "snapshot",
            {
                "snapshot_id": self.snapshot_id,
                "tenant_id": self.metadata.get("tenant_id"),
                "engagement_id": self.metadata.get("engagement_id"),
                "kind": self.manifest["kind"],
                "content_hash": self.content_hash,
                "location": str(self.path),
                "manifest": self.manifest,
                "sealed_at": self.manifest["sealed_at"],
            },
        )

    def close(self) -> None:
        self.con.close()
