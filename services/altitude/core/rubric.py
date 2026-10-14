"""Rubrics: every score threshold, weight and estimation factor lives here as data.

Rubric files live in ``knowledge/rubrics/*.yaml``::

    namespace: compute
    version: 1.0.0
    values:
      auto_suspend_max_seconds: 60

Application code refers to values by reference (``rubric.compute.auto_suspend_max_seconds``),
never by literal. ``RubricSet.version`` identifies the exact values used so any
score or estimate can be reproduced.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import KnowledgeValidationError, RubricReferenceError
from .ids import content_hash
from .paths import knowledge_dir

REF_PREFIX = "rubric."


def is_ref(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(REF_PREFIX)


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


@dataclass
class RubricSet:
    namespaces: dict[str, dict[str, Any]]
    versions: dict[str, str]
    overrides: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None, overrides: dict[str, Any] | None = None) -> "RubricSet":
        root = root or (knowledge_dir() / "rubrics")
        namespaces: dict[str, dict[str, Any]] = {}
        versions: dict[str, str] = {}
        problems: list[str] = []
        for path in sorted(root.glob("*.yaml")):
            try:
                doc = yaml.safe_load(path.read_text()) or {}
            except yaml.YAMLError as e:
                mark = getattr(e, "problem_mark", None)
                problems.append(f"{path}{':' + str(mark.line + 1) if mark else ''}: YAML parse error")
                continue
            ns = doc.get("namespace") if isinstance(doc, dict) else None
            if not ns or "values" not in doc or "version" not in doc:
                problems.append(f"{path}: rubric requires 'namespace', 'version' and 'values'")
                continue
            if ns in namespaces:
                problems.append(f"{path}: duplicate rubric namespace '{ns}'")
                continue
            namespaces[ns] = doc["values"] or {}
            versions[ns] = str(doc["version"])
        if problems:
            raise KnowledgeValidationError(problems)
        rs = cls(namespaces=namespaces, versions=versions)
        if overrides:
            rs = rs.with_overrides(overrides)
        return rs

    def with_overrides(self, overrides: dict[str, Any]) -> "RubricSet":
        """Tenant-specific overrides, e.g. ``{"compute": {"auto_suspend_max_seconds": 120}}``."""
        merged = {ns: _deep_merge(vals, overrides.get(ns, {})) for ns, vals in self.namespaces.items()}
        for ns in overrides:
            if ns not in merged:
                raise RubricReferenceError(f"override for unknown rubric namespace '{ns}'")
        return RubricSet(merged, dict(self.versions), _deep_merge(self.overrides, overrides))

    @property
    def version(self) -> str:
        """Stable identifier: namespace versions plus a hash of the effective values."""
        tag = ",".join(f"{ns}@{v}" for ns, v in sorted(self.versions.items()))
        return f"rubric:{content_hash({'v': tag, 'values': self.namespaces}, 12)}"

    def get(self, ref: str, default: Any = ...) -> Any:
        if not is_ref(ref):
            raise RubricReferenceError(f"not a rubric reference: {ref!r}")
        parts = ref[len(REF_PREFIX):].split(".")
        node: Any = self.namespaces
        for i, part in enumerate(parts):
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                if default is not ...:
                    return default
                raise RubricReferenceError(
                    f"unresolved rubric reference {ref!r} (missing '{'.'.join(parts[: i + 1])}')"
                )
        return node

    def resolve(self, value: Any) -> Any:
        """Resolve a value that may be a rubric reference (recursively for containers)."""
        if is_ref(value):
            return self.get(value)
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value

    def has(self, ref: str) -> bool:
        return self.get(ref, default=None) is not None


_cache: dict[str, RubricSet] = {}


def default_rubrics() -> RubricSet:
    key = str(knowledge_dir())
    if key not in _cache:
        _cache[key] = RubricSet.load()
    return _cache[key]
