"""EAIRN 8-pillar AI-readiness scoring on Snowflake (Section 19), computed from a sealed snapshot.

Each check (``knowledge/airready/checks.yaml``) yields NUMERATOR / DENOMINATOR -> a score in [0, 1]
(not applicable when the denominator is 0). Pillar score = 100 x weighted mean of applicable check scores;
overall = weighted mean of pillar scores (weights in ``rubric.airready``); maturity level from the rubric bands.

Reproducible per snapshot: the report depends only on the snapshot content, the rubric version, the check
set and the KPI registry (all recorded) — the same inputs give a byte-identical report and ``score_hash``.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import duckdb

from altitude.core.errors import KnowledgeValidationError
from altitude.core.ids import canonical_json, content_hash
from altitude.core.knowledge import load_entries
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import json_safe

from . import kpi_registry

PILLARS = ("data_quality", "governance", "metadata", "security", "ai_engineering", "semantic_layer",
           "agent_readiness", "rag_readiness")
PARAM_RE = re.compile(r"\$([a-z_]+)")


def load_checks(root: Path | None = None) -> list[dict]:
    return sorted(load_entries("airready/checks*.yaml", "checks", root), key=lambda c: c["id"])


def cross_check(checks: list[dict], root: Path | None = None) -> list[str]:
    playbooks = {p["id"] for p in load_entries("playbooks/*.yaml", "playbooks", root)}
    problems = []
    for c in checks:
        if c["playbook"] not in playbooks:
            problems.append(f"{c['_source']}: {c['id']}: unknown playbook {c['playbook']}")
        for name in set(PARAM_RE.findall(c["query"])) - {"as_of", "kpi_names"} - set(c.get("params", {})):
            problems.append(f"{c['_source']}: {c['id']}: query parameter ${name} is not bound")
    missing = set(PILLARS) - {c["pillar"] for c in checks}
    if missing:
        problems.append(f"airready checks: no check for pillar(s) {sorted(missing)}")
    return problems


@dataclass
class CheckResult:
    check_id: str
    pillar: str
    title: str
    numerator: float | None
    denominator: float | None
    score: float | None          # None => not applicable
    pass_mark: float
    passed: bool | None
    weight: float
    gaps: list[str]
    playbook: str
    rationale: str


@dataclass
class ReadinessReport:
    snapshot_id: str
    snapshot_hash: str
    rubric_version: str
    checks_version: str
    registry_version: str
    checks: list[CheckResult]
    pillars: dict[str, dict]
    overall: float
    maturity_level: int
    maturity_label: str
    priorities: list[dict]

    def to_dict(self) -> dict:
        d = json_safe(asdict(self))
        d["score_hash"] = self.score_hash
        return d

    @property
    def score_hash(self) -> str:
        return content_hash(json_safe(asdict(self)), 16)

    def check(self, check_id: str) -> CheckResult:
        return next(c for c in self.checks if c.check_id == check_id)


def _float(v: Any) -> float | None:
    return float(v) if v is not None else None


def score(snapshot: Any, rubrics: RubricSet | None = None, checks: list[dict] | None = None,
          registry: kpi_registry.Registry | None = None) -> ReadinessReport:
    rubrics = rubrics or default_rubrics()
    checks = checks if checks is not None else load_checks()
    registry = registry or kpi_registry.load()
    problems = cross_check(checks)
    if problems:
        raise KnowledgeValidationError(problems)
    meta = getattr(snapshot, "metadata", {}) or {}
    values: dict[str, Any] = {"as_of": f"{meta['window_end']} 23:59:59" if meta.get("window_end") else None,
                              "kpi_names": registry.names()}
    weights = rubrics.get("rubric.airready.check_weights")
    results: list[CheckResult] = []
    for c in checks:
        bound = dict(values)
        for name, ref in c.get("params", {}).items():
            bound[name] = rubrics.get(ref)
        params = {k: v for k, v in bound.items() if k in set(PARAM_RE.findall(c["query"]))}
        pass_mark = float(rubrics.get(c["threshold_ref"]))
        try:
            rows = snapshot.query(c["query"], params)
        except duckdb.CatalogException:
            rows = []
        row = rows[0] if rows else {}
        num, den = _float(row.get("NUMERATOR")), _float(row.get("DENOMINATOR"))
        s = round(num / den, 6) if num is not None and den else None
        results.append(CheckResult(
            check_id=c["id"], pillar=c["pillar"], title=c["title"], numerator=num, denominator=den, score=s,
            pass_mark=pass_mark, passed=(s >= pass_mark) if s is not None else None,
            weight=float(weights[c["weight"]]), gaps=sorted(str(g) for g in (row.get("GAPS") or [])),
            playbook=c["playbook"], rationale=c["rationale"]))

    pw = rubrics.get("rubric.airready.pillar_weights")
    pillars: dict[str, dict] = {}
    for p in PILLARS:
        app = [r for r in results if r.pillar == p and r.score is not None]
        total = sum(r.weight for r in app)
        pillars[p] = {
            "score": round(100.0 * sum(r.score * r.weight for r in app) / total, 1) if total else None,
            "checks": len([r for r in results if r.pillar == p]), "applicable": len(app),
            "passed": len([r for r in app if r.passed]), "weight": float(pw[p])}
    scored = [(v["score"], v["weight"]) for v in pillars.values() if v["score"] is not None]
    wsum = sum(w for _, w in scored)
    overall = round(sum(s * w for s, w in scored) / wsum, 1) if wsum else 0.0
    band = next(b for b in rubrics.get("rubric.airready.maturity_bands") if overall >= b["min"])
    failing = [r for r in results if r.passed is False]
    failing.sort(key=lambda r: (-(r.weight * (r.pass_mark - (r.score or 0.0))), r.check_id))
    priorities = [{"check_id": r.check_id, "pillar": r.pillar, "title": r.title, "score": r.score,
                   "pass_mark": r.pass_mark, "playbook": r.playbook, "gaps": r.gaps[:10]} for r in failing]
    knowledge = [{k: v for k, v in c.items() if k != "_source"} for c in checks]
    return ReadinessReport(
        snapshot_id=getattr(snapshot, "snapshot_id", "adhoc"), snapshot_hash=getattr(snapshot, "content_hash", ""),
        rubric_version=rubrics.version, checks_version="AIR-" + content_hash(canonical_json(knowledge), 12).upper(),
        registry_version=registry.version, checks=results, pillars=pillars, overall=overall,
        maturity_level=int(band["level"]), maturity_label=band["label"], priorities=priorities)


def persist(store: Any, report: ReadinessReport) -> bool:
    key = {"snapshot_id": report.snapshot_id, "rubric_version": report.rubric_version,
           "checks_version": report.checks_version}
    existing = store.get("airready_score", **key)
    if existing:
        if existing["score_hash"] != report.score_hash:
            raise KnowledgeValidationError([f"readiness score for {key} is not reproducible: "
                                            f"{existing['score_hash']} != {report.score_hash}"])
        return False
    store.insert("airready_score", {**key, "registry_version": report.registry_version, "overall": report.overall,
                                    "maturity_level": report.maturity_level, "pillars": report.pillars,
                                    "score_hash": report.score_hash})
    return True


def to_markdown(report: ReadinessReport) -> str:
    out = [f"# AI readiness (EAIRN) — {report.snapshot_id}", "",
           f"**{report.overall} / 100 — level {report.maturity_level} ({report.maturity_label})**", "",
           f"Snapshot `{report.snapshot_hash}` · rubric `{report.rubric_version}` · checks `{report.checks_version}` · "
           f"KPI registry `{report.registry_version}` · score `{report.score_hash}`", "",
           "| Pillar | Score | Passed |", "|---|---|---|"]
    for p, v in report.pillars.items():
        out.append(f"| {p} | {v['score'] if v['score'] is not None else 'n/a'} | {v['passed']}/{v['applicable']} |")
    out += ["", "## Priorities", "", "| Check | Pillar | Score | Pass mark | Playbook | Gaps |", "|---|---|---|---|---|---|"]
    for r in report.priorities:
        out.append(f"| {r['check_id']} {r['title']} | {r['pillar']} | {r['score']} | {r['pass_mark']} | "
                   f"{r['playbook']} | {', '.join(r['gaps'][:5])} |")
    return "\n".join(out) + "\n"


__all__ = ["PILLARS", "ReadinessReport", "load_checks", "persist", "score", "to_markdown"]
