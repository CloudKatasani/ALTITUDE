"""Well-Architected checker (Section 14): run WA-* checks (knowledge-as-data, Section 14.9 format) over a
sealed snapshot and report findings with their remediation playbooks.

Reproducible: the result depends only on the snapshot content, the rubric version and the check/playbook
knowledge (``checks_version``); it carries all three plus a ``report_hash``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb

from altitude.core.ids import content_hash
from altitude.core.knowledge import load_entries
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import json_safe

PARAM_RE = re.compile(r"\$([a-z_]+)")
SEVERITIES = ("critical", "high", "medium", "low")


def load_checks(root: Path | None = None) -> list[dict]:
    return sorted(load_entries("well_architected/checks/*.yaml", "checks", root), key=lambda c: c["id"])


def load_playbooks(root: Path | None = None) -> dict[str, dict]:
    return {p["id"]: p for p in load_entries("playbooks/*.yaml", "playbooks", root)}


def query_ref(check_id: str) -> str:
    return f"generated/foundation/sql/{check_id.lower().replace('-', '_')}.sql"


def cross_check(checks: list[dict], playbooks: dict[str, dict]) -> list[str]:
    """Referential integrity between checks and playbooks."""
    problems = []
    for c in checks:
        pb = c["remediation"]["playbook"]
        if pb not in playbooks:
            problems.append(f"{c['_source']}: {c['id']}: unknown playbook {pb}")
        if c.get("query_ref") and c["query_ref"] != query_ref(c["id"]):
            problems.append(f"{c['_source']}: {c['id']}: query_ref must be {query_ref(c['id'])}")
        if "$threshold" in c["query"] and not c.get("threshold_ref"):
            problems.append(f"{c['_source']}: {c['id']}: query uses $threshold but has no threshold_ref")
        for name in set(PARAM_RE.findall(c["query"])) - {"threshold", "as_of"} - set(c.get("params", {})):
            problems.append(f"{c['_source']}: {c['id']}: query parameter ${name} is not bound")
    return problems


@dataclass
class WAFinding:
    check_id: str
    pillar: str
    waf_pillar: str
    section: str
    title: str
    severity: str
    rationale: str
    objects: list[str]
    evidence: list[dict]
    threshold_ref: str | None
    threshold: Any
    autonomy: str
    auto_fix_available: bool
    playbook: dict
    remediation_sql: list[str] = field(default_factory=list)
    rollback_sql: list[str] = field(default_factory=list)


@dataclass
class WAReport:
    snapshot_id: str
    snapshot_hash: str
    rubric_version: str
    checks_version: str
    as_of: str | None
    findings: list[WAFinding]
    passed: list[str]
    not_applicable: list[dict]
    pillar_scores: dict[str, float]
    waf_pillar_scores: dict[str, float]
    overall: float
    rating: str

    def to_dict(self) -> dict:
        d = json_safe(asdict(self))
        d["report_hash"] = self.report_hash
        return d

    @property
    def report_hash(self) -> str:
        return content_hash(json_safe(asdict(self)), 16)

    def finding(self, check_id: str) -> WAFinding | None:
        return next((f for f in self.findings if f.check_id == check_id), None)


def _rating(score: float, rubrics: RubricSet) -> str:
    bands = rubrics.get("rubric.foundation.pillar_rating_bands")
    if score >= bands["strong"]:
        return "strong"
    if score >= bands["adequate"]:
        return "adequate"
    return "weak"


def _score(applicable: list[dict], failing: set[str], key: str, weights: dict) -> dict[str, float]:
    totals: dict[str, float] = {}
    fails: dict[str, float] = {}
    for c in applicable:
        w = float(weights[c["severity"]])
        totals[c[key]] = totals.get(c[key], 0.0) + w
        if c["id"] in failing:
            fails[c[key]] = fails.get(c[key], 0.0) + w
    return {k: round(100.0 * (1 - fails.get(k, 0.0) / t), 1) for k, t in sorted(totals.items()) if t}


def run(snapshot: Any, rubrics: RubricSet | None = None, checks: list[dict] | None = None,
        playbooks: dict[str, dict] | None = None) -> WAReport:
    """Run every WA check over ``snapshot`` (a sealed :class:`~altitude.core.snapshot.Snapshot`)."""
    rubrics = rubrics or default_rubrics()
    checks = checks if checks is not None else load_checks()
    playbooks = playbooks if playbooks is not None else load_playbooks()
    problems = cross_check(checks, playbooks)
    if problems:
        from altitude.core.errors import KnowledgeValidationError

        raise KnowledgeValidationError(problems)
    meta = getattr(snapshot, "metadata", {}) or {}
    as_of = f"{meta['window_end']} 23:59:59" if meta.get("window_end") else None
    max_rows = int(rubrics.get("rubric.foundation.max_evidence_rows"))
    findings, passed, na = [], [], []
    applicable = []
    for c in checks:
        values: dict[str, Any] = {"as_of": as_of}
        if c.get("threshold_ref"):
            values["threshold"] = rubrics.get(c["threshold_ref"])
        for name, ref in c.get("params", {}).items():
            values[name] = rubrics.get(ref)
        used = set(PARAM_RE.findall(c["query"]))
        params = {k: v for k, v in values.items() if k in used}
        if "as_of" in used and as_of is None:
            na.append({"check_id": c["id"], "reason": "snapshot has no window_end"})
            continue
        try:
            rows = snapshot.query(c["query"], params)
        except duckdb.CatalogException as e:
            na.append({"check_id": c["id"], "reason": f"evidence table missing: {str(e).splitlines()[0]}"})
            continue
        applicable.append(c)
        if not rows:
            passed.append(c["id"])
            continue
        objects = sorted({str(r["OBJECT_NAME"]) for r in rows if r.get("OBJECT_NAME") is not None})
        pb = playbooks[c["remediation"]["playbook"]]
        rem = [pb["remediation_sql"].format(object=o) for o in objects] if pb.get("remediation_sql") else []
        rb = [pb["rollback_sql"].format(object=o) for o in objects] if pb.get("rollback_sql") else []
        findings.append(WAFinding(
            check_id=c["id"], pillar=c["pillar"], waf_pillar=c["waf_pillar"], section=c["section"], title=c["title"],
            severity=c["severity"], rationale=c["rationale"], objects=objects,
            evidence=json_safe(rows[:max_rows]), threshold_ref=c.get("threshold_ref"), threshold=values.get("threshold"),
            autonomy=c["remediation"]["autonomy"], auto_fix_available=c["remediation"]["auto_fix_available"],
            playbook={k: v for k, v in pb.items() if not k.startswith("_")}, remediation_sql=rem, rollback_sql=rb))
    weights = rubrics.get("rubric.foundation.severity_weights")
    failing = {f.check_id for f in findings}
    pillar_scores = _score(applicable, failing, "pillar", weights)
    waf_scores = _score(applicable, failing, "waf_pillar", weights)
    overall = _score([{**c, "all": "all"} for c in applicable], failing, "all", weights).get("all", 100.0)
    knowledge = {"checks": [{k: v for k, v in c.items() if k != "_source"} for c in checks],
                 "playbooks": {k: {kk: vv for kk, vv in v.items() if kk != "_source"} for k, v in sorted(playbooks.items())}}
    findings.sort(key=lambda f: (SEVERITIES.index(f.severity), f.check_id))
    return WAReport(snapshot_id=getattr(snapshot, "snapshot_id", "adhoc"),
                    snapshot_hash=getattr(snapshot, "content_hash", ""), rubric_version=rubrics.version,
                    checks_version="WA-" + content_hash(knowledge, 12).upper(), as_of=as_of, findings=findings,
                    passed=sorted(passed), not_applicable=na, pillar_scores=pillar_scores, waf_pillar_scores=waf_scores,
                    overall=overall, rating=_rating(overall, rubrics))


def persist(store: Any, report: WAReport) -> int:
    """Record findings (idempotent per snapshot + rubric version + checks version)."""
    n = 0
    for f in report.findings:
        key = {"snapshot_id": report.snapshot_id, "rubric_version": report.rubric_version,
               "checks_version": report.checks_version, "check_id": f.check_id}
        if store.get("wa_finding", **key):
            continue
        store.insert("wa_finding", {**key, "severity": f.severity, "pillar": f.pillar, "objects": f.objects,
                                    "playbook_id": f.playbook["id"], "autonomy": f.autonomy,
                                    "evidence": {"rows": f.evidence}})
        n += 1
    return n


def to_markdown(report: WAReport) -> str:
    out = [f"# Well-Architected check — {report.snapshot_id}", "",
           f"Snapshot hash `{report.snapshot_hash}` · rubric `{report.rubric_version}` · checks `{report.checks_version}` "
           f"· report `{report.report_hash}`", "",
           f"**Overall {report.overall} ({report.rating})** — {len(report.findings)} finding(s), "
           f"{len(report.passed)} passed, {len(report.not_applicable)} not applicable.", "",
           "| Pillar | Score |", "|---|---|"]
    out += [f"| {p} | {s} |" for p, s in report.waf_pillar_scores.items()]
    out += ["", "| Check | Severity | Title | Objects | Playbook | Autonomy |", "|---|---|---|---|---|---|"]
    for f in report.findings:
        objs = ", ".join(f.objects[:6]) + (" …" if len(f.objects) > len(f.objects[:6]) else "")
        out.append(f"| {f.check_id} | {f.severity} | {f.title} | {objs} | {f.playbook['id']}: {f.playbook['title']} | "
                   f"{f.autonomy} |")
    for f in report.findings:
        out += ["", f"## {f.check_id} — {f.title}", "", f"*{f.rationale}*", "",
                f"Threshold: `{f.threshold_ref}` = {f.threshold}" if f.threshold_ref else "Threshold: n/a", "",
                f"Playbook **{f.playbook['id']}** ({f.playbook['risk']} risk, ~{f.playbook['effort_hours']}h): "
                f"{f.playbook['summary']}", ""]
        out += [f"{i}. {s}" for i, s in enumerate(f.playbook["steps"], 1)]
        if f.remediation_sql:
            out += ["", "```sql"] + [s + ";" for s in f.remediation_sql] + ["```"]
    return "\n".join(out) + "\n"
