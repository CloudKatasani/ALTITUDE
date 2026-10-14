"""Published permission manifests (``knowledge/connectors/<source>.yaml``).

A manifest lists the grants the extraction agent needs, why each is needed,
and the exact catalog objects it reads. ``objects_read`` doubles as the scope
of the :class:`~altitude_connectors.readonly.ReadOnlyConnection`: a statement
touching any object not listed is refused, so user tables cannot be read.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from altitude.core.errors import ReadOnlyViolation
from altitude.core.paths import knowledge_dir

#: Privileges a manifest may request. Anything else (INSERT, ALTER, db_owner, ...) is refused.
READ_PRIVILEGES = frozenset({
    "SELECT", "VIEW DEFINITION", "VIEW ANY DEFINITION", "VIEW SERVER STATE", "VIEW DATABASE STATE",
    "SQLAgentReaderRole", "ssis_logreader", "SELECT_CATALOG_ROLE", "AUDIT_VIEWER", "CREATE SESSION", "LOGON",
})


@dataclass(frozen=True)
class Manifest:
    id: str
    source: str
    dialect: str
    version: str
    doc: dict[str, Any]

    @property
    def scope(self) -> list[str]:
        return [o["name"] for o in self.doc["objects_read"]]

    @property
    def grants(self) -> list[dict[str, Any]]:
        return list(self.doc["required_grants"])

    @property
    def file_globs(self) -> list[str]:
        return [f["glob"] for f in self.doc.get("files_read", [])]

    def summary(self) -> dict[str, Any]:
        return {"id": self.id, "version": self.version, "source": self.source,
                "grants": [g["privilege"] for g in self.grants], "objects_read": self.scope}


def assert_read_only(doc: dict[str, Any]) -> None:
    for g in doc.get("required_grants", []):
        if g.get("privilege") not in READ_PRIVILEGES:
            raise ReadOnlyViolation(f"manifest {doc.get('id')} requests non-read privilege {g.get('privilege')!r}")
    if doc.get("row_data") is not False:
        raise ReadOnlyViolation(f"manifest {doc.get('id')} must declare row_data: false")


def load_manifest(source: str, root: Path | None = None) -> Manifest:
    root = root or knowledge_dir()
    path = root / "connectors" / f"{source}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"no permission manifest published for source {source!r} ({path})")
    doc = yaml.safe_load(path.read_text())
    assert_read_only(doc)
    return Manifest(id=doc["id"], source=doc["source"], dialect=doc["dialect"], version=doc["version"], doc=doc)


def available_sources(root: Path | None = None) -> list[str]:
    root = root or knowledge_dir()
    return sorted(p.stem for p in (root / "connectors").glob("*.yaml"))
