"""Skill adapters for the conversion orchestrator (``altitude.conversion``)."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from .context import coerce
from .impl_common import out_dir, safe
from .registry import SkillError

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def convert_module(context: Any = None, source_sql: str = "", dialect: str = "", name: str = "module.sql",
                   engagement_id: str = "ENG-LOCAL", source_system_id: str = "source",
                   remediate: bool = False) -> dict:
    """Convert one module of legacy SQL to Snowflake (SnowConvert AI when installed, else the sqlglot fallback)."""
    from altitude.conversion.orchestrator import ConversionOrchestrator, select_converter
    from altitude.core.ids import content_hash

    ctx = coerce(context)
    fname = _SAFE_NAME.sub("_", Path(name).name) or "module.sql"
    src_dir = out_dir(ctx, "convert_module", "source", content_hash([dialect, fname, source_sql], 12))
    (src_dir / fname).write_text(source_sql)
    orch = ConversionOrchestrator(ctx.store, engagement_id, rubrics=ctx.rubrics, converter=select_converter(),
                                  source_system_id=source_system_id)
    run = orch.run(src_dir, dialect, out_dir(ctx, "convert_module", "out"))
    artifacts = []
    for aid in run.artifact_ids:
        art = ctx.store.get("converted_artifact", artifact_id=aid)
        issues = ctx.store.query("SELECT issue_id, code, severity, message, line FROM conversion_issue "
                                 "WHERE artifact_id = ? ORDER BY line, issue_id", [aid])
        content = ctx.store.get("artifact_content", artifact_id=aid, kind="converted")["content"]
        artifacts.append({"artifact_id": aid, "object_id": art["object_id"], "target_path": art["target_path"],
                          "path": str(run.output_dir / "converted" / art["target_path"]),
                          "issues": len(issues), "issues_by_severity": dict(sorted(Counter(i["severity"] for i in issues).items())),
                          "issue_codes": dict(sorted(Counter(i["code"] for i in issues).items())),
                          "issue_list": issues, "converted_sql": content})
    out = {"run_id": run.run_id, "tool": run.tool, "tool_version": run.tool_version, "dialect": dialect,
           "issue_count": run.issue_count, "artifacts": artifacts}
    if remediate:
        out["remediation"] = _remediate(ctx, run.artifact_ids)
    return safe(out)


def _artifact_ids(ctx: Any, artifact_id: str | None, run_id: str | None) -> list[str]:
    if artifact_id:
        if ctx.store.get("converted_artifact", artifact_id=artifact_id) is None:
            raise SkillError(f"unknown artifact {artifact_id!r}")
        return [artifact_id]
    if run_id:
        rows = ctx.store.query("SELECT artifact_id FROM converted_artifact WHERE run_id = ? ORDER BY target_path",
                               [run_id])
        if not rows:
            raise SkillError(f"conversion run {run_id!r} has no artifacts")
        return [r["artifact_id"] for r in rows]
    raise SkillError("one of artifact_id or run_id is required")


def _agent(ctx: Any):
    from altitude.conversion.remediation import RemediationAgent

    return RemediationAgent(ctx.store, packs_root=out_dir(ctx, "remediate_ewis", "pr_packs"), rubrics=ctx.rubrics)


def _remediate(ctx: Any, artifact_ids: list[str]) -> list[dict]:
    agent = _agent(ctx)
    out = []
    for aid in artifact_ids:
        res = agent.remediate(aid)
        out.append({"artifact_id": aid, "pack_id": res.pack_id, "pack_dir": str(res.pack_dir),
                    "changes": [{"change_id": c.change_id, "rules": c.rule_ids, "issue_codes": c.issue_codes,
                                 "lines": [c.line_start, c.line_end], "confidence": c.confidence,
                                 "below_review_floor": c.below_floor, "tests": c.tests} for c in res.changes],
                    "unresolved_issue_ids": res.unresolved_issue_ids})
    return out


def remediate_ewis(context: Any = None, artifact_id: str | None = None, run_id: str | None = None) -> dict:
    """AI remediation of EWIs/known issues into a PR pack (diffs, tests, review checklist); never production."""
    ctx = coerce(context)
    packs = _remediate(ctx, _artifact_ids(ctx, artifact_id, run_id))
    return safe({"packs": packs, "changes": sum(len(p["changes"]) for p in packs),
                 "unresolved": sum(len(p["unresolved_issue_ids"]) for p in packs),
                 "below_review_floor": sum(1 for p in packs for c in p["changes"] if c["below_review_floor"])})


def generate_unit_tests(context: Any = None, artifact_id: str | None = None, run_id: str | None = None,
                        run: bool = True) -> dict:
    """Generated unit tests for each AI change (from the PR pack's ai_change records); optionally run them."""
    from altitude.conversion.remediation import run_pack_tests

    ctx = coerce(context)
    agent = _agent(ctx)
    out = []
    for aid in _artifact_ids(ctx, artifact_id, run_id):
        res = agent.remediate(aid)  # idempotent: returns the existing pack when already remediated
        changes = ctx.store.query("SELECT change_id, tests_generated, decision FROM ai_change WHERE artifact_id = ? "
                                  "ORDER BY change_id", [aid])
        item = {"artifact_id": aid, "pack_id": res.pack_id,
                "test_files": sorted(str(p) for p in (Path(res.pack_dir) / "tests").glob("test_*.py")),
                "tests_by_change": {c["change_id"]: list(c["tests_generated"] or []) for c in changes},
                "tests": sum(len(c["tests_generated"] or []) for c in changes)}
        if run:
            report = run_pack_tests(Path(res.pack_dir))  # against the proposed files/ (or final/ once reviewed)
            item["run"] = {"total": report.total, "passed": report.passed, "failures": report.failures,
                           "pass_rate": round(report.pass_rate, 4)}
        out.append(item)
    return safe({"artifacts": out, "tests": sum(a["tests"] for a in out)})
