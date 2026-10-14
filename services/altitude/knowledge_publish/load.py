"""Publish knowledge YAML into the canonical tables (``pattern``, ``known_issue``, ``fix_pattern``,
``test_case``, ``rubric``, ``rubric_version``).

YAML stays the source of truth; the tables are published copies used by the portal, API and
the native edition. Publishing is idempotent. Two governance rules are enforced:

- the knowledge base must validate (schemas, rubric references, unique ids) before publishing;
- a rubric namespace whose values changed must also bump its version (published versions are
  immutable, so scores computed against them stay reproducible).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from altitude.core.errors import KnowledgeValidationError
from altitude.core.ids import canonical_json
from altitude.core.knowledge import validate_tree
from altitude.core.paths import knowledge_dir
from altitude.core.rubric import RubricSet
from altitude.patterns.library import PatternLibrary


@dataclass
class PublishResult:
    patterns: int
    known_issues: int
    fix_patterns: int
    test_cases: int
    rubrics: int
    rubric_versions_added: int

    def as_dict(self) -> dict[str, int]:
        return dict(self.__dict__)


def _rubric_docs(root: Path) -> list[dict]:
    docs = []
    for p in sorted((root / "rubrics").glob("*.yaml")):
        d = yaml.safe_load(p.read_text())
        docs.append({"namespace": d["namespace"], "version": str(d["version"]), "values": d["values"] or {}})
    return docs


def publish(store, root: Path | None = None, now: datetime | None = None, validate: bool = True) -> PublishResult:
    root = Path(root or knowledge_dir())
    if validate:
        problems = validate_tree(root)
        if problems:
            raise KnowledgeValidationError(problems)
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    lib = PatternLibrary.load(root)
    rubrics = RubricSet.load(root / "rubrics")

    # governance: a changed rubric must carry a new version
    changed = []
    docs = _rubric_docs(root)
    for d in docs:
        prev = store.get("rubric_version", namespace=d["namespace"], version=d["version"])
        if prev is not None:
            stored = prev["values"]
            stored = json.loads(stored) if isinstance(stored, str) else stored
            if canonical_json(stored) != canonical_json(d["values"]):
                changed.append(f"rubrics/{d['namespace']}.yaml: values changed but version {d['version']} "
                               f"is already published; bump the version")
    if changed:
        raise KnowledgeValidationError(changed)

    frequency = {r["issue_id"]: r["frequency_observed"] for r in store.query(
        "SELECT issue_id, frequency_observed FROM known_issue")}
    for table in ("pattern", "known_issue", "fix_pattern", "test_case"):
        store.execute(f'DELETE FROM "{table}"')

    store.insert("pattern", [{
        "pattern_id": m["id"], "source_dialect": m["source_dialect"], "source_construct": m["source_construct"],
        "target_construct": m["target_construct"], "note": m.get("note") or None,
        "last_verified": date.fromisoformat(m["last_verified"]),
    } for m in sorted(lib.mappings, key=lambda m: m["id"])])
    issues = sorted(lib.issues.values(), key=lambda i: i.id)
    store.insert("known_issue", [{
        "issue_id": i.id, "source_dialect": i.source_dialect, "title": i.title, "severity": i.severity,
        "detection_rule": i.detection["detector"], "fix_pattern_id": i.primary_fix.id,
        "test_case_ids": list(i.tests), "frequency_observed": int(frequency.get(i.id) or 0),
        "last_verified": date.fromisoformat(i.last_verified), "verified_by": i.verified_by,
    } for i in issues])
    fixes = [{"fix_pattern_id": f.id, "issue_id": i.id, "description": f.description, "applies_when": f.applies_when}
             for i in issues for f in i.fix_patterns]
    store.insert("fix_pattern", fixes)
    tests = [{"test_case_id": tid, "issue_id": tc["issue_id"], "description": tc["description"],
              "definition": {k: v for k, v in tc.items() if not k.startswith("_")}}
             for tid, tc in sorted(lib.tests.items())]
    store.insert("test_case", tests)

    added = 0
    for d in docs:
        if store.get("rubric_version", namespace=d["namespace"], version=d["version"]) is None:
            store.insert("rubric_version", {"namespace": d["namespace"], "version": d["version"],
                                            "rubric_set_version": rubrics.version, "values": d["values"],
                                            "published_at": now})
            added += 1
        if store.get("rubric", namespace=d["namespace"]):
            store.update("rubric", {"namespace": d["namespace"]}, {"current_version": d["version"]})
        else:
            store.insert("rubric", {"namespace": d["namespace"], "current_version": d["version"]})
    return PublishResult(len(lib.mappings), len(issues), len(fixes), len(tests), len(docs), added)


def record_observation(store, issue_id: str, n: int = 1) -> int:
    """Anonymised frequency counter: an engagement observed ``issue_id`` ``n`` more times."""
    row = store.get("known_issue", issue_id=issue_id)
    if row is None:
        raise KeyError(issue_id)
    total = int(row["frequency_observed"] or 0) + int(n)
    store.update("known_issue", {"issue_id": issue_id}, {"frequency_observed": total})
    return total
