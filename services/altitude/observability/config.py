"""Loaders for Package O knowledge: sources, tenant registries, curated model, KPIs, alerts, runbooks."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from altitude.core.paths import knowledge_dir

OBS_DIR = "observability"


def obs_dir(root: Path | None = None) -> Path:
    return (root or knowledge_dir()) / OBS_DIR


@lru_cache(maxsize=256)
def _parse(path: str, mtime_ns: int, size: int) -> Any:
    return yaml.safe_load(Path(path).read_text())


def read_yaml(path: Path) -> Any:
    """Parse a knowledge YAML file, cached until the file changes; callers get their own copy."""
    st = path.stat()
    return copy.deepcopy(_parse(str(path), st.st_mtime_ns, st.st_size))


@dataclass(frozen=True)
class SourceConfig:
    table: str
    domain: str
    strategy: str  # incremental | merge | full_snapshot
    schedule: str
    freshness_sla_ref: str
    watermark: str | None = None
    key: tuple[str, ...] = ()
    native_retention_days: int | None = None
    live: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def is_snapshot(self) -> bool:
        return self.strategy == "full_snapshot"


def load_sources(root: Path | None = None) -> list[SourceConfig]:
    doc = read_yaml(obs_dir(root) / "sources.yaml")
    out = []
    for s in doc["sources"]:
        out.append(SourceConfig(
            table=s["table"], domain=s["domain"], strategy=s["strategy"], schedule=s["schedule"],
            freshness_sla_ref=s["freshness_sla_ref"], watermark=s.get("watermark"), key=tuple(s.get("key", [])),
            native_retention_days=s.get("native_retention_days"), live=dict(s.get("live") or {}),
        ))
    return out


def sources_defaults(root: Path | None = None) -> dict:
    return dict(read_yaml(obs_dir(root) / "sources.yaml").get("defaults") or {})


def load_registry(path: str | Path | None = None) -> dict:
    """Tenant accounts registry (``knowledge/observability/accounts/*.yaml`` or any path)."""
    p = Path(path) if path else obs_dir() / "accounts" / "example_tenant.yaml"
    return read_yaml(p)


def load_curated(root: Path | None = None) -> list[dict]:
    return list(read_yaml(obs_dir(root) / "curated.yaml")["objects"])


def load_kpis(root: Path | None = None) -> list[dict]:
    out: list[dict] = []
    for p in sorted((obs_dir(root) / "kpis").glob("*.yaml")):
        doc = read_yaml(p) or {}
        for k in doc.get("kpis", []):
            out.append({**k, "_source": f"{OBS_DIR}/kpis/{p.name}"})
    return out


def kpi_index(root: Path | None = None) -> dict[str, dict]:
    return {k["id"]: k for k in load_kpis(root)}


def load_alerts(root: Path | None = None) -> dict:
    return read_yaml(obs_dir(root) / "alerts.yaml")


def load_runbooks(root: Path | None = None) -> dict[str, dict]:
    out = {}
    for p in sorted((obs_dir(root) / "runbooks").glob("*.yaml")):
        doc = read_yaml(p)
        out[doc["id"]] = doc
    return out


def load_golden(root: Path | None = None) -> list[dict]:
    return list(read_yaml(obs_dir(root) / "golden_questions.yaml")["questions"])


def kpi_table(kpi_id: str) -> str:
    """KPI table name for a KPI id: ``KPI-COST-001`` → ``KPI_COST_001``."""
    return kpi_id.replace("-", "_")


def resolve_route(registry: dict, route_ref: str) -> tuple[str, dict]:
    """``tenant.alert_routes.finops`` → ``("finops", {channel, target, ...})``."""
    prefix = "tenant.alert_routes."
    if not route_ref.startswith(prefix):
        raise KeyError(f"route_ref must start with {prefix!r}: {route_ref!r}")
    name = route_ref[len(prefix):]
    routes = registry.get("alert_routes") or {}
    if name not in routes:
        raise KeyError(f"tenant {registry.get('tenant_id')} has no alert route {name!r}")
    return name, dict(routes[name])


def as_list(v: Any) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]
