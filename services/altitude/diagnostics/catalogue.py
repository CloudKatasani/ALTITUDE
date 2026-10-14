"""Check catalogue, domains, tiers, recommender and helper relations — all loaded from ``knowledge/diagnostics``.

Nothing about *what* is checked lives in code: detectors, rules, value/risk models, remediation
templates and KPIs are YAML (schema-governed, see ``altitude/core/schemas/diagnostics_*.json``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

import yaml

from altitude.core.paths import knowledge_dir
from altitude.core.rubric import RubricSet

PARAM_RE = re.compile(r"\$([a-z_][a-z0-9_]*)")

# Parameters every detector may reference; bound by the engine from the snapshot and the rubric.
STANDARD_PARAMS = (
    "window_start", "window_end", "window_days", "as_of", "price_per_credit", "storage_price_per_tb_month",
    "days_per_year", "days_per_month", "months_per_year", "minutes_per_hour", "ms_per_second", "ms_per_hour",
    "bytes_per_gb", "bytes_per_tb",
)
UNIT_REFS = {
    "days_per_year": "rubric.diagnostics.units.days_per_year",
    "days_per_month": "rubric.diagnostics.units.days_per_month",
    "months_per_year": "rubric.diagnostics.units.months_per_year",
    "minutes_per_hour": "rubric.diagnostics.units.minutes_per_hour",
    "ms_per_second": "rubric.diagnostics.units.ms_per_second",
    "ms_per_hour": "rubric.diagnostics.units.ms_per_hour",
    "bytes_per_gb": "rubric.diagnostics.units.bytes_per_gb",
    "bytes_per_tb": "rubric.diagnostics.units.bytes_per_tb",
}


@dataclass(frozen=True)
class Check:
    raw: dict

    @property
    def id(self) -> str:
        return self.raw["id"]

    @property
    def title(self) -> str:
        return self.raw["title"]

    @property
    def domain(self) -> str:
        return self.raw["domain"]

    @property
    def scored_domains(self) -> list[str]:
        return [self.domain, *self.raw.get("also_scores", [])]

    @property
    def waf_pillar(self) -> str:
        return self.raw["waf_pillar"]

    @property
    def severity(self) -> str:
        return self.raw["severity"]

    @property
    def detector(self) -> dict:
        return self.raw["detector"]

    @property
    def requires(self) -> list[str]:
        return list(self.detector["requires"])

    @property
    def inputs(self) -> list[str]:
        return list(self.detector.get("inputs", []))

    @property
    def cluster_by(self) -> str:
        return self.detector["cluster_by"]

    @property
    def key(self) -> str:
        """Rubric key for this check, e.g. ``DX-COST-01`` -> ``cost_01``."""
        _, area, num = self.id.split("-")
        return f"{area.lower()}_{num}"

    def detector_sql(self) -> str:
        """The executable detector: signals wrapped with the rule as a FLAGGED column."""
        return (
            f"WITH __signals AS (\n{self.detector['signals'].rstrip().rstrip(';')}\n)\n"
            f"SELECT *, coalesce(({self.detector['rule']}), false) AS FLAGGED\n"
            f"FROM __signals\nORDER BY OBJECT_NAME, CLUSTER_KEY"
        )

    def referenced_params(self) -> list[str]:
        text = self.detector["signals"] + "\n" + self.detector["rule"]
        return sorted(set(PARAM_RE.findall(text)))

    def resolve_params(self, rubrics: RubricSet) -> dict[str, Any]:
        """Check-specific parameters: thresholds/refs resolved from the rubric, values as given."""
        out: dict[str, Any] = {}
        for name, spec in sorted(self.detector.get("params", {}).items()):
            if "threshold_ref" in spec:
                out[name] = rubrics.get(spec["threshold_ref"])
            elif "ref" in spec:
                out[name] = rubrics.get(spec["ref"])
            else:
                out[name] = spec["value"]
        return out

    def param_sources(self) -> dict[str, str]:
        out = {}
        for name, spec in sorted(self.detector.get("params", {}).items()):
            out[name] = spec.get("threshold_ref") or spec.get("ref") or "value"
        return out


@dataclass
class Catalogue:
    checks: list[Check]
    domains: list[dict]
    pillars: list[dict]
    tiers: list[dict]
    recommendations: list[dict]
    helpers: list[dict]
    sources: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "Catalogue":
        root = root or knowledge_dir()
        base = root / "diagnostics"
        checks: list[Check] = []
        sources: dict[str, str] = {}
        for path in sorted((base / "checks").glob("*.yaml")):
            doc = yaml.safe_load(path.read_text()) or {}
            for item in doc.get("checks", []):
                checks.append(Check(item))
                sources[item["id"]] = path.relative_to(root).as_posix()
        checks.sort(key=lambda c: c.id)
        domains_doc = yaml.safe_load((base / "domains.yaml").read_text())
        tiers_doc = yaml.safe_load((base / "tiers.yaml").read_text())
        rec_doc = yaml.safe_load((base / "recommender.yaml").read_text())
        helpers_doc = yaml.safe_load((base / "helpers.yaml").read_text())
        return cls(
            checks=checks,
            domains=domains_doc["domains"],
            pillars=domains_doc["waf_pillars"],
            tiers=tiers_doc["tiers"],
            recommendations=rec_doc["recommendations"],
            helpers=helpers_doc["helpers"],
            sources=sources,
        )

    @cached_property
    def by_id(self) -> dict[str, Check]:
        return {c.id: c for c in self.checks}

    def check(self, check_id: str) -> Check:
        return self.by_id[check_id]

    def tier(self, tier: str) -> dict:
        for t in self.tiers:
            if t["tier"] == tier:
                return t
        raise KeyError(f"unknown diagnostics tier {tier!r} (known: {', '.join(t['tier'] for t in self.tiers)})")

    def domain(self, domain_id: str) -> dict:
        for d in self.domains:
            if d["id"] == domain_id:
                return d
        raise KeyError(domain_id)

    def checks_for_tier(self, tier: str) -> list[Check]:
        scope = set(self.tier(tier)["domains"])
        return [c for c in self.checks if c.domain in scope]


_cache: dict[str, Catalogue] = {}


def default_catalogue() -> Catalogue:
    key = str(knowledge_dir())
    if key not in _cache:
        _cache[key] = Catalogue.load()
    return _cache[key]
