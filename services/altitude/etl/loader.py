"""Detect and parse ETL / scheduler exports by content, and persist results to the control plane."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from altitude.core.ids import content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .classify import JobAssessment
from .controlm import parse_controlm
from .graph import PackageParse
from .informatica import parse_powercenter
from .scheduler import SchedulerConversion, SchedulerDAG
from .sqlagent import parse_sqlagent
from .ssis import parse_dtsx


def detect(path: str | Path) -> str:
    """ssis | informatica | controlm | sqlagent."""
    path = Path(path)
    if path.suffix.lower() == ".dtsx":
        return "ssis"
    if path.suffix.lower() == ".sql":
        if "sp_add_job" in path.read_text(errors="replace"):
            return "sqlagent"
        raise ValueError(f"{path}: SQL file is not a SQL Agent job script")
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        raise ValueError(f"{path}: not XML: {e}") from e
    tag = root.tag.split("}")[-1]
    if tag == "POWERMART":
        return "informatica"
    if tag == "DEFTABLE" or root.find(".//JOB") is not None:
        return "controlm"
    if tag == "Executable":
        return "ssis"
    raise ValueError(f"{path}: unrecognised export (root element {tag})")


def load_packages(paths: list[str | Path]) -> list[PackageParse]:
    out: list[PackageParse] = []
    for p in paths:
        kind = detect(p)
        if kind == "ssis":
            out.append(parse_dtsx(p))
        elif kind == "informatica":
            out += parse_powercenter(p)
        else:
            raise ValueError(f"{p}: {kind} is a scheduler export, not an ETL package")
    return out


def load_schedules(path: str | Path) -> list[SchedulerDAG]:
    kind = detect(path)
    if kind == "controlm":
        return parse_controlm(path)
    if kind == "sqlagent":
        return [parse_sqlagent(path)]
    raise ValueError(f"{path}: {kind} is an ETL package, not a scheduler export")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def record_assessments(store: Any, engagement_id: str, assessments: list[JobAssessment],
                       rubrics: RubricSet | None = None) -> list[str]:
    rubrics = rubrics or default_rubrics()
    ids = []
    for a in assessments:
        job_id = stable_id("ETLJ", engagement_id, a.tool, a.source_file, a.job, length=10)
        row = {"job_id": job_id, "engagement_id": engagement_id, "tool": a.tool, "source_file": a.source_file,
               "name": a.job, "classification": a.classification, "recommendation": a.recommendation,
               "complexity_score": a.complexity_score, "confidence": round(a.confidence, 3),
               "rationale": a.rationale, "graph_hash": a.graph_hash or content_hash(a.rationale),
               "issues": [vars(i) for i in a.issues] or None, "rubric_version": rubrics.version,
               "created_at": _now()}
        if store.get("etl_job", job_id=job_id):
            store.update("etl_job", {"job_id": job_id}, {k: v for k, v in row.items() if k != "job_id"})
        else:
            store.insert("etl_job", row)
        ids.append(job_id)
    return ids


def record_scheduler(store: Any, engagement_id: str, conv: SchedulerConversion) -> str:
    dag = conv.dag
    dag_id = stable_id("SDAG", engagement_id, dag.tool, dag.source_file, dag.name, length=10)
    row = {"dag_id": dag_id, "engagement_id": engagement_id, "tool": dag.tool, "source_file": dag.source_file,
           "job_count": len(dag.jobs), "edge_count": len(dag.edges()), "task_sql_hash": content_hash(conv.task_sql),
           "airflow_hash": content_hash(conv.airflow), "issues": [vars(i) for i in dag.issues] or None,
           "created_at": _now()}
    if store.get("scheduler_dag", dag_id=dag_id):
        store.update("scheduler_dag", {"dag_id": dag_id}, {k: v for k, v in row.items() if k != "dag_id"})
    else:
        store.insert("scheduler_dag", row)
    return dag_id
