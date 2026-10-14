"""Data types shared by the Pattern Library, detectors and the semantic-drift checker."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

STRENGTHS = ("strong", "medium", "weak")
SEVERITY_ORDER = {"S1": 0, "S2": 1, "S3": 2, "S4": 3}

CHECKLIST = {
    1: "Case sensitivity (identifiers and data)",
    2: "NULL vs empty string",
    3: "Numeric precision/scale and integer division",
    4: "Date vs timestamp; time-zone policy (NTZ/LTZ/TZ)",
    5: "Trailing spaces / CHAR padding",
    6: "Duplicate handling (SET tables, unenforced constraints)",
    7: "Sort order / collation in ORDER BY, MIN/MAX on strings",
    8: "Nondeterministic UPDATE...FROM / MERGE with multi-match sources",
    9: "Implicit casts",
    10: "Floating-point aggregation order",
    11: "Session parameters (date formats, week start, TIMESTAMP_TYPE_MAPPING)",
    12: "Transaction/commit semantics in procedures (autocommit, DDL implicit commits)",
}


@dataclass(frozen=True)
class Finding:
    """Raw output of a detector, before it is bound to a known issue."""

    line: int
    snippet: str
    message: str
    strength: str
    rationale: str

    def __post_init__(self) -> None:
        if self.strength not in STRENGTHS:
            raise ValueError(f"invalid detector strength {self.strength!r}")


@dataclass(frozen=True)
class DriftHit:
    """One semantic-drift hit: public result type of :func:`altitude.patterns.scan_sql`.

    ``line`` is 1-based (0 for profile/metadata hits); ``confidence`` comes from
    ``rubric.patterns.detector_confidence``; ``checklist_item`` is the primary
    Section 10.13 checklist item (1-12) or ``None`` for operational issues.
    """

    issue_id: str
    severity: str
    line: int
    snippet: str
    message: str
    confidence: float
    rationale: str
    checklist_item: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FixPattern:
    id: str
    description: str
    applies_when: str


@dataclass
class KnownIssue:
    id: str
    source_dialect: str
    applies_to: tuple[str, ...]
    title: str
    severity: str
    checklist_items: tuple[int, ...]
    symptoms: tuple[str, ...]
    detection: dict
    fix_patterns: tuple[FixPattern, ...]
    tests: tuple[str, ...]
    validation_normalisation: str
    mismatch_signatures: tuple[str, ...]
    decision_required: bool
    last_verified: str
    verified_by: str
    source_file: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def detectors(self) -> tuple[str, ...]:
        return (self.detection["detector"], *self.detection.get("extra_detectors", []))

    @property
    def primary_checklist_item(self) -> int | None:
        return self.checklist_items[0] if self.checklist_items else None

    @property
    def primary_fix(self) -> FixPattern:
        return self.fix_patterns[0]

    @classmethod
    def from_dict(cls, d: dict) -> "KnownIssue":
        applies = d.get("applies_to") or [d["source_dialect"]]
        return cls(
            id=d["id"],
            source_dialect=d["source_dialect"],
            applies_to=tuple(applies),
            title=d["title"],
            severity=d["severity"],
            checklist_items=tuple(d.get("checklist_items", [])),
            symptoms=tuple(d.get("symptoms", [])),
            detection=dict(d["detection"]),
            fix_patterns=tuple(FixPattern(f["id"], f["description"], f["applies_when"]) for f in d["fix_patterns"]),
            tests=tuple(d.get("tests", [])),
            validation_normalisation=d.get("validation_normalisation", ""),
            mismatch_signatures=tuple(d.get("mismatch_signatures", [])),
            decision_required=bool(d.get("decision_required", False)),
            last_verified=str(d["last_verified"]),
            verified_by=d["verified_by"],
            source_file=d.get("_source", ""),
            raw={k: v for k, v in d.items() if k != "_source"},
        )
