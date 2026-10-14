"""Validation knowledge: tier levels, normalisation rules and triage signatures (``knowledge/validation``)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from altitude.core.paths import knowledge_dir

LEVELS = ("L0", "L1", "L2", "L3", "L4", "L5")
MODES = ("full", "sample", "none")


@dataclass(frozen=True)
class NormRule:
    id: str
    op: str
    applies_to: tuple[str, ...]
    always: bool
    policy: str | None
    params: dict = field(default_factory=dict, hash=False, compare=False)
    linked_issues: tuple[str, ...] = ()
    description: str = ""


@dataclass(frozen=True)
class Signature:
    id: str
    signature: str
    description: str
    issue_by_dialect: dict = field(hash=False, compare=False)
    confidence_ref: str = ""


@dataclass
class ValidationKnowledge:
    levels_version: str
    levels: dict[str, dict]                # L0 -> {name, description}
    tiers: dict[str, dict]                 # tier1 -> {description, levels: {L0: mode}, threshold_ref}
    normalisation_version: str
    rules: list[NormRule]
    signatures_version: str
    signatures: dict[str, Signature]       # signature name -> Signature

    @classmethod
    def load(cls, root: Path | None = None) -> "ValidationKnowledge":
        base = Path(root or knowledge_dir()) / "validation"
        lv = yaml.safe_load((base / "levels.yaml").read_text())
        nr = yaml.safe_load((base / "normalisation.yaml").read_text())
        sg = yaml.safe_load((base / "triage_signatures.yaml").read_text())
        rules = [NormRule(r["id"], r["op"], tuple(r["applies_to"]), bool(r.get("always", False)), r.get("policy"),
                          dict(r.get("params") or {}), tuple(r.get("linked_issues", [])), r.get("description", ""))
                 for r in nr["rules"]]
        sigs = {s["signature"]: Signature(s["id"], s["signature"], s["description"], dict(s["issue_by_dialect"]),
                                          s["confidence_ref"]) for s in sg["signatures"]}
        return cls(
            levels_version=str(lv["version"]),
            levels={x["id"]: x for x in lv["levels"]},
            tiers={t["id"]: t for t in lv["tiers"]},
            normalisation_version=str(nr["version"]),
            rules=rules,
            signatures_version=str(sg["version"]),
            signatures=sigs,
        )

    def tier(self, tier: str) -> dict:
        if tier not in self.tiers:
            raise ValueError(f"unknown tier {tier!r}; expected one of {', '.join(self.tiers)}")
        return self.tiers[tier]

    @property
    def policies(self) -> list[str]:
        return sorted({r.policy for r in self.rules if r.policy})


@lru_cache(maxsize=4)
def _cached(root: str) -> ValidationKnowledge:
    return ValidationKnowledge.load(Path(root))


def default_knowledge() -> ValidationKnowledge:
    return _cached(str(knowledge_dir()))
