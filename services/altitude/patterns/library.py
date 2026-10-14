"""Loader for the Pattern Library (``knowledge/dialects/**``).

Layout (Section 31)::

    knowledge/dialects/<dialect>/mappings.yaml       conversion map
    knowledge/dialects/<dialect>/known_issues.yaml   known-issues register (Appendix A)
    knowledge/dialects/<dialect>/tests/*.yaml        golden / detector / profile test cases

``common`` holds cross-source issues that declare ``applies_to`` dialects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from altitude.core.paths import knowledge_dir

from .model import SEVERITY_ORDER, KnownIssue

DIALECTS = ("teradata", "oracle", "sqlserver", "netezza", "redshift")
DIALECT_ALIASES = {
    "td": "teradata", "bteq": "teradata",
    "ora": "oracle", "plsql": "oracle", "exadata": "oracle",
    "mssql": "sqlserver", "tsql": "sqlserver", "sql_server": "sqlserver", "azuresql": "sqlserver",
    "synapse": "sqlserver",
    "nz": "netezza", "puredata": "netezza",
    "rs": "redshift",
}


def normalise_dialect(dialect: str) -> str:
    d = (dialect or "").strip().lower().replace("-", "_")
    d = DIALECT_ALIASES.get(d, d)
    if d not in DIALECTS:
        raise ValueError(f"unsupported source dialect {dialect!r}; expected one of {', '.join(DIALECTS)}")
    return d


@dataclass
class PatternLibrary:
    root: Path
    issues: dict[str, KnownIssue] = field(default_factory=dict)
    mappings: list[dict] = field(default_factory=list)
    tests: dict[str, dict] = field(default_factory=dict)
    versions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path | None = None) -> "PatternLibrary":
        root = Path(root or knowledge_dir())
        lib = cls(root=root)
        base = root / "dialects"
        for path in sorted(base.glob("*/known_issues.yaml")):
            doc = yaml.safe_load(path.read_text()) or {}
            lib.versions[f"{doc.get('dialect')}/known_issues"] = str(doc.get("version", ""))
            for item in doc.get("known_issues", []):
                item = dict(item, _source=path.relative_to(root).as_posix())
                issue = KnownIssue.from_dict(item)
                if issue.id in lib.issues:
                    raise ValueError(f"duplicate known issue id {issue.id}")
                lib.issues[issue.id] = issue
        for path in sorted(base.glob("*/mappings.yaml")):
            doc = yaml.safe_load(path.read_text()) or {}
            lib.versions[f"{doc.get('dialect')}/mappings"] = str(doc.get("version", ""))
            for m in doc.get("mappings", []):
                lib.mappings.append(dict(m, source_dialect=doc["dialect"], _source=path.relative_to(root).as_posix()))
        for path in sorted(base.glob("*/tests/*.yaml")):
            doc = yaml.safe_load(path.read_text()) or {}
            for tc in doc.get("test_cases", []):
                if tc["id"] in lib.tests:
                    raise ValueError(f"duplicate test case id {tc['id']}")
                lib.tests[tc["id"]] = dict(tc, dialect=doc["dialect"], _source=path.relative_to(root).as_posix())
        return lib

    # ------------------------------------------------------------------ queries
    def issues_for(self, dialect: str) -> list[KnownIssue]:
        d = normalise_dialect(dialect)
        out = [i for i in self.issues.values() if d in i.applies_to]
        return sorted(out, key=lambda i: (SEVERITY_ORDER[i.severity], i.id))

    def issue(self, issue_id: str) -> KnownIssue:
        return self.issues[issue_id]

    def fix_pattern(self, fix_id: str):
        for issue in self.issues.values():
            for f in issue.fix_patterns:
                if f.id == fix_id:
                    return issue, f
        raise KeyError(fix_id)

    def tests_for(self, issue_id: str) -> list[dict]:
        return [t for t in self.tests.values() if t["issue_id"] == issue_id]

    def scan_dialect_of(self, test: dict) -> str:
        if test.get("scan_dialect"):
            return normalise_dialect(test["scan_dialect"])
        if test["dialect"] in DIALECTS:
            return test["dialect"]
        return normalise_dialect(self.issues[test["issue_id"]].applies_to[0])

    @property
    def version(self) -> str:
        from altitude.core.ids import content_hash

        content = {
            "versions": self.versions,
            "issues": {k: v.raw for k, v in sorted(self.issues.items())},
            "mappings": self.mappings,
            "tests": self.tests,
        }
        return f"patterns:{content_hash(content, 12)}"


@lru_cache(maxsize=4)
def _cached(root: str) -> PatternLibrary:
    return PatternLibrary.load(Path(root))


def default_library() -> PatternLibrary:
    return _cached(str(knowledge_dir()))
