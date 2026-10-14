"""Semantic-drift checker (Section 10.13): run Pattern Library detectors over source code or metadata.

Public API (imported by the assessment engine — keep the signature)::

    from altitude.patterns import scan_sql, DriftHit
    hits: list[DriftHit] = scan_sql(sql, "teradata")
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Iterable

from altitude.core.rubric import RubricSet, default_rubrics

from .detectors import ensure_loaded, get
from .library import PatternLibrary, default_library, normalise_dialect
from .model import CHECKLIST, SEVERITY_ORDER, DriftHit, Finding, KnownIssue
from .source import SourceContext

log = logging.getLogger(__name__)

CONFIDENCE_REF = "rubric.patterns.detector_confidence.{}"
SNIPPET_REF = "rubric.patterns.scan.snippet_max_chars"


@dataclass
class Scanner:
    library: PatternLibrary = field(default_factory=default_library)
    rubrics: RubricSet = field(default_factory=default_rubrics)
    strict: bool = False   # re-raise detector errors (tests/golden runner) instead of skipping the detector

    def __post_init__(self) -> None:
        ensure_loaded()

    # ------------------------------------------------------------------ binding
    def _bind(self, issue: KnownIssue, f: Finding) -> DriftHit:
        limit = int(self.rubrics.get(SNIPPET_REF))
        snippet = f.snippet if len(f.snippet) <= limit else f.snippet[: limit - 1] + "…"
        fix = issue.primary_fix
        return DriftHit(
            issue_id=issue.id,
            severity=issue.severity,
            line=f.line,
            snippet=snippet,
            message=f"{issue.title} — {f.message}",
            confidence=float(self.rubrics.get(CONFIDENCE_REF.format(f.strength))),
            rationale=f"{f.rationale} Fix {fix.id}: {fix.description}",
            checklist_item=issue.primary_checklist_item,
        )

    def _run(self, kind: str, dialect: str, payload, issues: Iterable[KnownIssue] | None = None) -> list[DriftHit]:
        cache: dict[str, list[Finding]] = {}
        best: dict[tuple[str, int, str], DriftHit] = {}
        for issue in issues if issues is not None else self.library.issues_for(dialect):
            for name in issue.detectors:
                det = get(name)
                if det.kind != kind:
                    continue
                if name not in cache:
                    try:
                        cache[name] = list(det.func(payload, self.rubrics))
                    except Exception:  # noqa: BLE001 - one bad detector must not sink a whole scan
                        if self.strict:
                            raise
                        log.warning("detector %s failed; skipped", name, exc_info=True)
                        cache[name] = []
                for f in cache[name]:
                    h = self._bind(issue, f)
                    key = (h.issue_id, h.line, h.snippet if kind == "profile" else "")
                    if key not in best or h.confidence > best[key].confidence:
                        best[key] = h
        return sorted(best.values(), key=lambda h: (h.line, SEVERITY_ORDER[h.severity], h.issue_id, h.snippet))

    # ------------------------------------------------------------------ public
    def scan_sql(self, sql: str, dialect: str) -> list[DriftHit]:
        d = normalise_dialect(dialect)
        return self._run("static", d, SourceContext(sql, d))

    def scan_profile(self, profile: dict, dialect: str) -> list[DriftHit]:
        d = normalise_dialect(dialect)
        return self._run("profile", d, profile)

    def coverage(self, dialect: str) -> dict[int, list[str]]:
        """Checklist item -> known issues (with an executable detector) covering it for ``dialect``."""
        out: dict[int, list[str]] = {i: [] for i in CHECKLIST}
        for issue in self.library.issues_for(dialect):
            for item in issue.checklist_items:
                out[item].append(issue.id)
        return out


def scan_sql(sql: str, dialect: str) -> list[DriftHit]:
    """Scan source code for semantic drift against Snowflake. Returns hits sorted by line."""
    return Scanner().scan_sql(sql, dialect)


def scan_profile(profile: dict, dialect: str) -> list[DriftHit]:
    """Run profile detectors over harvested metadata/aggregate statistics (see ``detectors.profile``)."""
    return Scanner().scan_profile(profile, dialect)


# --------------------------------------------------------------------------- reports


def report(hits: list[DriftHit], dialect: str, source: str = "<sql>", scanner: Scanner | None = None) -> dict:
    scanner = scanner or Scanner()
    d = normalise_dialect(dialect)
    cov = scanner.coverage(d)
    by_sev: dict[str, int] = {s: 0 for s in SEVERITY_ORDER}
    for h in hits:
        by_sev[h.severity] += 1
    checklist = []
    items_of = {i.id: set(i.checklist_items) for i in scanner.library.issues.values()}
    for item, title in CHECKLIST.items():
        item_hits = [h for h in hits if item in items_of.get(h.issue_id, {h.checklist_item})]
        checklist.append({
            "item": item,
            "title": title,
            "covered_by": cov[item],
            "hits": len(item_hits),
            "status": "flagged" if item_hits else ("clear" if cov[item] else "not_covered"),
        })
    return {
        "source": source,
        "dialect": d,
        "pattern_library_version": scanner.library.version,
        "rubric_version": scanner.rubrics.version,
        "summary": {"hits": len(hits), "by_severity": by_sev},
        "checklist": checklist,
        "hits": [h.to_dict() for h in hits],
    }


def render_json(rep: dict) -> str:
    return json.dumps(rep, indent=2, sort_keys=False) + "\n"


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_md(rep: dict) -> str:
    s = rep["summary"]
    lines = [
        f"# Semantic-drift report: `{rep['source']}` ({rep['dialect']})",
        "",
        f"Pattern Library `{rep['pattern_library_version']}` · rubric `{rep['rubric_version']}` · "
        f"{s['hits']} hit(s): " + ", ".join(f"{k}={v}" for k, v in s["by_severity"].items()),
        "",
        "## Section 10.13 checklist",
        "",
        "| # | Item | Status | Hits | Known issues |",
        "|---|---|---|---|---|",
    ]
    for c in rep["checklist"]:
        lines.append(f"| {c['item']} | {_cell(c['title'])} | {c['status']} | {c['hits']} | "
                     f"{', '.join(c['covered_by']) or '—'} |")
    lines += ["", "## Hits", ""]
    if not rep["hits"]:
        lines.append("No drift detected.")
    else:
        lines += ["| Line | Issue | Sev | Conf | Finding | Snippet |", "|---|---|---|---|---|---|"]
        for h in rep["hits"]:
            lines.append(f"| {h['line']} | {h['issue_id']} | {h['severity']} | {h['confidence']:.2f} | "
                         f"{_cell(h['message'])} | `{_cell(h['snippet'])}` |")
    return "\n".join(lines) + "\n"


def render_text(rep: dict) -> str:
    out = [f"{rep['source']}: {rep['summary']['hits']} drift hit(s) [{rep['dialect']}]"]
    for h in rep["hits"]:
        out.append(f"  {rep['source']}:{h['line']}: {h['issue_id']} [{h['severity']}] "
                   f"({h['confidence']:.2f}) {h['message']}")
    return "\n".join(out) + "\n"
