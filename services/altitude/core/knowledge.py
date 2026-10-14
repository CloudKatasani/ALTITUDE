"""Knowledge-as-data: loader and validator for everything under ``knowledge/``.

Each JSON schema in ``altitude/core/schemas`` (and any module's ``schemas``
directory registered via ``SCHEMA_DIRS``) declares which knowledge files it
governs with an ``x-altitude-globs`` list, e.g.::

    {"x-altitude-globs": ["dialects/*/known_issues.yaml"], ...}

Every YAML file under ``knowledge/`` must be governed by exactly one schema.
Validation errors are precise: ``<file>:<line>: <json-path>: <message>``.
Beyond the schema, every ``rubric.*`` reference must resolve and fields named
``*_ref`` that point at thresholds must be references, not literals.
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Iterator

import jsonschema
import yaml

from .errors import KnowledgeValidationError
from .paths import knowledge_dir
from .rubric import RubricSet, is_ref

SCHEMA_DIRS: list[Path] = [Path(__file__).parent / "schemas"]


@dataclass(frozen=True)
class SchemaEntry:
    name: str
    globs: tuple[str, ...]
    schema: dict


def register_schema_dir(path: Path) -> None:
    if path not in SCHEMA_DIRS:
        SCHEMA_DIRS.append(path)
        _schemas.cache_clear()


@lru_cache(maxsize=1)
def _schemas() -> tuple[SchemaEntry, ...]:
    entries = []
    for d in SCHEMA_DIRS:
        for p in sorted(d.glob("*.json")):
            schema = json.loads(p.read_text())
            globs = tuple(schema.get("x-altitude-globs", []))
            if globs:
                entries.append(SchemaEntry(p.stem, globs, schema))
    return tuple(entries)


def schema_for(rel_path: str) -> SchemaEntry | None:
    matches = [e for e in _schemas() if any(fnmatch.fnmatch(rel_path, g) for g in e.globs)]
    if len(matches) > 1:
        raise KnowledgeValidationError(
            [f"{rel_path}: governed by more than one schema: {', '.join(m.name for m in matches)}"]
        )
    return matches[0] if matches else None


# --------------------------------------------------------------------------- line mapping


def _line_index(text: str) -> dict[tuple, int]:
    """Map JSON paths (tuples of keys/indices) to 1-based source lines."""
    index: dict[tuple, int] = {}
    try:
        root = yaml.compose(text)
    except yaml.YAMLError:
        return index

    def walk(node: yaml.Node, path: tuple) -> None:
        index.setdefault(path, node.start_mark.line + 1)
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                key = k.value
                index[path + (key,)] = k.start_mark.line + 1
                walk(v, path + (key,))
        elif isinstance(node, yaml.SequenceNode):
            for i, v in enumerate(node.value):
                walk(v, path + (i,))

    if root is not None:
        walk(root, ())
    return index


def _fmt_path(path: Iterable) -> str:
    out = "$"
    for p in path:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out


def _walk_values(obj: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    yield path, obj
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk_values(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _walk_values(v, path + (i,))


# --------------------------------------------------------------------------- validation


def validate_file(path: Path, root: Path, rubrics: RubricSet | None) -> list[str]:
    rel = path.relative_to(root).as_posix()
    text = path.read_text()
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        line = f":{mark.line + 1}" if mark else ""
        return [f"{rel}{line}: YAML parse error: {getattr(e, 'problem', e)}"]
    lines = _line_index(text)

    def where(p: tuple) -> str:
        for cut in range(len(p), -1, -1):
            if p[:cut] in lines:
                return f"{rel}:{lines[p[:cut]]}"
        return rel

    entry = schema_for(rel)
    if entry is None:
        return [f"{rel}: no schema governs this knowledge file (add x-altitude-globs to a schema)"]

    problems: list[str] = []
    validator = jsonschema.Draft202012Validator(entry.schema)
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(map(str, e.absolute_path))):
        p = tuple(err.absolute_path)
        problems.append(f"{where(p)}: {_fmt_path(p)}: {err.message}")

    for p, v in _walk_values(doc):
        key = p[-1] if p else None
        if isinstance(key, str) and key.endswith("threshold_ref") and not is_ref(v):
            problems.append(f"{where(p)}: {_fmt_path(p)}: threshold must be a rubric reference, got {v!r}")
        if rubrics is not None and is_ref(v) and not rel.startswith("rubrics/"):
            if not rubrics.has(v):
                problems.append(f"{where(p)}: {_fmt_path(p)}: unresolved rubric reference {v!r}")
    return problems


def validate_tree(root: Path | None = None) -> list[str]:
    root = root or knowledge_dir()
    problems: list[str] = []
    rubrics: RubricSet | None
    try:
        rubrics = RubricSet.load(root / "rubrics")
    except KnowledgeValidationError as e:
        problems.extend(e.problems)
        rubrics = None
    files = sorted(p for p in root.rglob("*.yaml") if not any(part.startswith(".") for part in p.parts))
    for path in files:
        problems.extend(validate_file(path, root, rubrics))
    problems.extend(_cross_file_checks(root))
    return problems


def _cross_file_checks(root: Path) -> list[str]:
    """IDs must be unique across the knowledge base (checks, issues, KPIs, ...)."""
    seen: dict[str, str] = {}
    problems: list[str] = []
    for path in sorted(root.rglob("*.yaml")):
        rel = path.relative_to(root).as_posix()
        if rel.startswith("rubrics/"):
            continue
        try:
            doc = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        for item in iter_entries(doc):
            ident = item.get("id")
            if isinstance(ident, str):
                if ident in seen and seen[ident] != rel:
                    problems.append(f"{rel}: duplicate id {ident!r} (also defined in {seen[ident]})")
                elif ident in seen:
                    problems.append(f"{rel}: duplicate id {ident!r}")
                seen[ident] = rel
    return problems


def iter_entries(doc: Any) -> Iterator[dict]:
    """Yield top-level entries: list items under any top-level list key, or the doc itself if it has an id."""
    if isinstance(doc, dict):
        if "id" in doc:
            yield doc
        for v in doc.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        yield item


def assert_valid(root: Path | None = None) -> None:
    problems = validate_tree(root)
    if problems:
        raise KnowledgeValidationError(problems)


# --------------------------------------------------------------------------- loading


def load_yaml(rel: str, root: Path | None = None) -> Any:
    root = root or knowledge_dir()
    return yaml.safe_load((root / rel).read_text())


def load_entries(pattern: str, key: str, root: Path | None = None) -> list[dict]:
    """Load and concatenate the list under ``key`` from every file matching ``pattern``.

    Each entry gets a ``_source`` attribute with its relative path.
    """
    root = root or knowledge_dir()
    out: list[dict] = []
    for path in sorted(root.glob(pattern)):
        doc = yaml.safe_load(path.read_text()) or {}
        items = doc.get(key, []) if isinstance(doc, dict) else []
        for item in items:
            item = dict(item)
            item["_source"] = path.relative_to(root).as_posix()
            out.append(item)
    return out
