"""Skill adapter for the ETL converters (``altitude.etl``)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .context import coerce
from .impl_common import out_dir, safe
from .registry import SkillError

_SAFE = re.compile(r"[^A-Za-z0-9_]+")


def generate_dbt_from_mapping(context: Any = None, files: list | None = None, project_name: str = "altitude_migration",
                              usage: dict | None = None, run: bool = False, engagement_id: str | None = None) -> dict:
    """Parse SSIS .dtsx / Informatica XML mappings and generate a stg_/int_/dim_/fct_ dbt project with tests."""
    from altitude.etl.dbt import generate_dbt_project
    from altitude.etl.loader import load_packages, record_assessments

    ctx = coerce(context)
    missing = [f for f in files or [] if not Path(f).exists()]
    if not files or missing:
        raise SkillError(f"mapping files not found: {missing or files}")
    name = _SAFE.sub("_", project_name).strip("_").lower() or "altitude_migration"
    packages = load_packages([Path(f) for f in files])
    project = generate_dbt_project(packages, name, usage, rubrics=ctx.rubrics)
    root = out_dir(ctx, "generate_dbt_from_mapping", name)
    for rel, content in sorted(project.files.items()):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(content)
    if engagement_id:
        record_assessments(ctx.store, engagement_id, project.assessments)
    out: dict[str, Any] = {
        "project": str(root), "project_name": name, "files": len(project.files),
        "models": sorted(project.models), "sources": sorted(".".join(k) for k in project.sources),
        "skipped": project.skipped,
        "jobs": [{"job": a.job, "tool": a.tool, "kind": a.kind, "classification": a.classification,
                  "recommendation": a.recommendation, "complexity": a.complexity_score, "confidence": a.confidence,
                  "issues": [i.id for i in a.issues], "blockers": a.blockers} for a in project.assessments],
        "recorded": bool(engagement_id),
    }
    if run:
        import duckdb

        from altitude.etl import synthetic
        from altitude.etl.harness import DbtHarness

        con = duckdb.connect()
        try:
            synthetic.load(con, project.sources, project.domains)
            res = DbtHarness(project.files).run(con)
        finally:
            con.close()
        out["run"] = {"ok": res.ok, "built": res.built, "errors": res.errors, "tests": len(res.tests),
                      "passed": sum(1 for t in res.tests if t.passed),
                      "failed": [f"{t.name} ({t.failures} rows)" for t in res.failed_tests]}
    return safe(out)
