"""Job classification (Section 11.1): passthrough / transform / complex, and retire / lift / re-engineer.

Complexity is a weighted count of mapping-graph steps plus known-issue severities; weights and thresholds
come from ``rubric.etl.*``. A job is ``complex`` when any step is not SQL-expressible (script components,
update strategies, mapplets, SQL overrides, untranslatable expressions) - verified by actually generating its
SQL - or when its score reaches ``rubric.etl.classification.complex_min_score``. Usage evidence (runs in the
last 90 days) proposes retirement. Every result carries confidence and rationale (principle 3).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from altitude.core.rubric import RubricSet, default_rubrics

from .graph import ControlTask, GraphIssue, MappingGraph, PackageParse
from .naming import ident
from .sqlgen import GenerationError, SqlBuilder


@dataclass
class JobAssessment:
    job: str
    tool: str
    package: str
    source_file: str
    kind: str                      # data_flow|control
    classification: str            # passthrough|transform|complex
    recommendation: str            # retire|lift|re-engineer
    complexity_score: float
    confidence: float
    rationale: str
    issues: list[GraphIssue] = field(default_factory=list)
    graph_hash: str = ""
    targets: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["issues"] = [asdict(i) for i in self.issues]
        return d


def _weight(rs: RubricSet, group: str, key: str) -> float:
    return float(rs.get(f"rubric.etl.{group}.{key}", default=rs.get(f"rubric.etl.{group}.unsupported")))


def _blockers(g: MappingGraph) -> list[str]:
    out = []
    for n in g.nodes.values():
        if n.kind == "unsupported":
            out.append(f"{n.name} ({n.tool_type}): {n.props.get('reason', 'not SQL-expressible')}")
        elif n.props.get("sql_override"):
            out.append(f"{n.name}: SQL override")
    if not out:
        for t in g.by_kind("target"):
            try:
                SqlBuilder(g, lambda node: f"{node.props.get('system')}.{node.props.get('table')}").build_target(t.id)
            except GenerationError as e:
                out.append(str(e))
    if not g.by_kind("target"):
        out.append("no target in data flow")
    return out


def classify_graph(g: MappingGraph, usage: dict[str, int] | None = None, rubrics: RubricSet | None = None) -> JobAssessment:
    rs = rubrics or default_rubrics()
    score = 0.0
    kinds: dict[str, int] = {}
    for n in g.nodes.values():
        kind = n.kind
        if kind == "project" and all(o.is_passthrough for o in n.props.get("outputs", [])) \
                and not (n.props.get("filter_sql") or n.props.get("filter") or n.props.get("distinct")):
            kind = "passthrough"
        if kind == "sort" and not n.props.get("distinct"):
            kind = "passthrough"
        kinds[kind] = kinds.get(kind, 0) + 1
        score += _weight(rs, "complexity_weights", kind)
    for issue in g.issues:
        score += float(rs.get(f"rubric.etl.issue_weights.{issue.severity}", default=0))
    blockers = _blockers(g)
    if blockers or score >= float(rs.get("rubric.etl.classification.complex_min_score")):
        cls = "complex"
    elif score <= float(rs.get("rubric.etl.classification.passthrough_max_score")):
        cls = "passthrough"
    else:
        cls = "transform"
    runs = None
    if usage is not None:
        runs = usage.get(g.job, usage.get(ident(g.job)))
    if runs is not None and runs <= int(rs.get("rubric.etl.usage.retire_max_runs_90d")):
        rec, conf = "retire", float(rs.get("rubric.etl.confidence.retire"))
    else:
        rec = "re-engineer" if cls == "complex" else "lift"
        conf = float(rs.get(f"rubric.etl.confidence.{cls}"))
    steps = ", ".join(f"{k}x{v}" for k, v in sorted(kinds.items()))
    issue_ids = sorted({i.id for i in g.issues})
    parts = [f"{cls} job ({steps}); complexity {score:g}"]
    if issue_ids:
        parts.append(f"known issues {', '.join(issue_ids)}")
    if blockers:
        parts.append("not SQL-expressible: " + "; ".join(blockers))
    if rec == "retire":
        parts.append(f"{runs} run(s) in the last 90 days")
    elif rec == "lift":
        parts.append("SQL-expressible end to end: generate dbt models")
    else:
        parts.append("re-engineer the blocked steps; generate the rest")
    return JobAssessment(
        job=g.job, tool=g.tool, package=g.package, source_file=g.source_file, kind="data_flow",
        classification=cls, recommendation=rec, complexity_score=score, confidence=conf,
        rationale="; ".join(parts), issues=list(g.issues), graph_hash=g.hash(),
        targets=[t.props.get("table") for t in g.by_kind("target")], blockers=blockers,
    )


def classify_task(task: ControlTask, pkg: PackageParse, usage: dict[str, int] | None = None,
                  rubrics: RubricSet | None = None) -> JobAssessment:
    rs = rubrics or default_rubrics()
    hint = task.recommendation_hint or "lift"
    score = sum(float(rs.get(f"rubric.etl.issue_weights.{i.severity}", default=0)) for i in task.issues)
    if hint == "re-engineer":
        cls, rec = "complex", "re-engineer"
        score += _weight(rs, "complexity_weights", "unsupported")
    elif hint == "retire":
        cls, rec = "passthrough", "retire"
    else:
        cls, rec = ("transform" if task.converted_sql else "passthrough"), "lift"
    conf = float(rs.get("rubric.etl.confidence.retire" if rec == "retire" else f"rubric.etl.confidence.{cls}"))
    why = [f"{task.kind} {task.name!r}"]
    if task.note:
        why.append(task.note)
    why += [i.message for i in task.issues]
    return JobAssessment(
        job=f"{pkg.package}::{task.name}", tool=pkg.tool, package=pkg.package, source_file=pkg.source_file,
        kind="control", classification=cls, recommendation=rec, complexity_score=score, confidence=conf,
        rationale="; ".join(why), issues=list(task.issues), targets=task.target_tables,
    )


def assess(packages: list[PackageParse], usage: dict[str, int] | None = None,
           rubrics: RubricSet | None = None) -> list[JobAssessment]:
    out = []
    for pkg in packages:
        out += [classify_graph(g, usage, rubrics) for g in pkg.graphs]
        out += [classify_task(t, pkg, usage, rubrics) for t in pkg.control_tasks]
    return out
