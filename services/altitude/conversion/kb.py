"""Loaders for ``knowledge/conversion/*.yaml`` (knowledge as data, principle 1)."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from altitude.core.knowledge import load_yaml
from altitude.core.paths import knowledge_dir


def _load(rel: str, root: Path | None) -> Any:
    return load_yaml(rel, root) or {}


@lru_cache(maxsize=8)
def _cached(rel: str, root: str) -> Any:
    return _load(rel, Path(root))


def load(rel: str, root: Path | None = None) -> Any:
    return _cached(rel, str(root or knowledge_dir()))


def snowconvert_config(root: Path | None = None) -> dict:
    return load("conversion/snowconvert.yaml", root)


def fallback_rules(root: Path | None = None) -> dict:
    return load("conversion/fallback_rules.yaml", root)


def remediation_rules(root: Path | None = None) -> list[dict]:
    return list(load("conversion/remediation_rules.yaml", root).get("rules", []))


def workflow(root: Path | None = None) -> dict:
    return load("conversion/workflow.yaml", root)


def prompts(root: Path | None = None) -> dict[str, dict]:
    return {p["id"]: p for p in load("conversion/prompts.yaml", root).get("prompts", [])}


def prompt_ref(prompt_id: str, root: Path | None = None) -> str:
    """``id@version`` for a prompt template (stored with every ai_change)."""
    p = prompts(root).get(prompt_id)
    if p is None:
        raise KeyError(f"unknown prompt template {prompt_id!r}")
    return f"{p['id']}@{p['version']}"


def severity_for(code: str, tool_severity: str | None, cfg: dict | None = None) -> tuple[str, str]:
    """Return (category, P-severity) for a tool issue code and its reported severity."""
    cfg = cfg or snowconvert_config()
    m = re.search(cfg["code_pattern"], code or "")
    category = m.group(1).upper() if m else "EWI"
    for ov in cfg.get("code_overrides", []):
        if ov["code"].upper() == (code or "").upper():
            return category, ov["severity"]
    sev = (tool_severity or "").strip()
    if re.fullmatch(r"(?i)P[1-4]", sev):
        return category, sev.upper()
    mapped = cfg["severity_map"].get(sev.lower())
    if mapped:
        return category, mapped
    return category, cfg["category_default_severity"].get(category, "P2")
