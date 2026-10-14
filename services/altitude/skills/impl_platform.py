"""Skill adapters for platform modules: Well-Architected (``altitude.foundation``), AI-readiness
(``altitude.airready``), semantic drift (``altitude.patterns``), ask-the-platform (``altitude.observability``)
and the run-operations agent fleet (``altitude_agents``)."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from typing import Any

from .context import coerce
from .impl_common import open_snapshot, out_dir, safe
from .registry import SkillError


def run_well_architected_check(context: Any = None, snapshot_id: str = "", persist: bool = True) -> dict:
    """Run the WA-* Well-Architected checks on a sealed snapshot; findings carry remediation playbooks."""
    from altitude.foundation import wa

    ctx = coerce(context)
    snap = open_snapshot(ctx, snapshot_id)
    report = wa.run(snap, rubrics=ctx.rubrics)
    if persist:
        wa.persist(ctx.store, report)
    md = out_dir(ctx, "run_well_architected_check") / f"{report.snapshot_id}-{report.report_hash}.md"
    md.write_text(wa.to_markdown(report))
    return safe({
        "snapshot_id": report.snapshot_id, "report_hash": report.report_hash, "rubric_version": report.rubric_version,
        "checks_version": report.checks_version, "overall": report.overall, "rating": report.rating,
        "pillar_scores": report.pillar_scores, "waf_pillar_scores": report.waf_pillar_scores,
        "passed": len(report.passed), "not_applicable": len(report.not_applicable),
        "findings_by_severity": dict(sorted(Counter(f.severity for f in report.findings).items())),
        "findings": [{"check_id": f.check_id, "pillar": f.pillar, "severity": f.severity, "title": f.title,
                      "playbook": f.playbook.get("id"), "autonomy": f.autonomy,
                      "auto_fix_available": f.auto_fix_available, "objects": f.objects[:10],
                      "object_count": len(f.objects)} for f in report.findings],
        "report_path": str(md), "persisted": persist,
    })


def score_ai_readiness(context: Any = None, snapshot_id: str = "", persist: bool = True) -> dict:
    """EAIRN eight-pillar AI-readiness score for a sealed snapshot, with the prioritised gaps to fix."""
    from altitude.airready import scoring

    ctx = coerce(context)
    snap = open_snapshot(ctx, snapshot_id)
    report = scoring.score(snap, rubrics=ctx.rubrics)
    if persist:
        scoring.persist(ctx.store, report)
    md = out_dir(ctx, "score_ai_readiness") / f"{report.snapshot_id}-{report.score_hash}.md"
    md.write_text(scoring.to_markdown(report))
    return safe({
        "snapshot_id": report.snapshot_id, "score_hash": report.score_hash, "rubric_version": report.rubric_version,
        "checks_version": report.checks_version, "overall": report.overall,
        "maturity_level": report.maturity_level, "maturity_label": report.maturity_label,
        "pillars": {p: {"score": v.get("score"), "passed": v.get("passed"), "applicable": v.get("applicable")}
                    for p, v in report.pillars.items()},
        "checks": len(report.checks), "priorities": report.priorities[:10], "gaps": len(report.priorities),
        "report_path": str(md), "persisted": persist,
    })


def scan_drift(context: Any = None, sql: str = "", dialect: str = "", source: str = "<sql>") -> dict:
    """Static semantic-drift scan of legacy SQL against Snowflake semantics (Pattern Library detectors)."""
    from altitude.patterns.library import normalise_dialect
    from altitude.patterns.scan import Scanner, report

    try:
        d = normalise_dialect(dialect)
    except ValueError as e:
        raise SkillError(str(e)) from None
    scanner = Scanner()
    hits = scanner.scan_sql(sql, d)
    rep = report(hits, d, source, scanner)
    return safe({**{k: rep[k] for k in ("source", "dialect", "pattern_library_version", "rubric_version", "summary")},
                 "issues": sorted({h.issue_id for h in hits}),
                 "checklist_flagged": [c["item"] for c in rep["checklist"] if c["status"] == "flagged"],
                 "hits": rep["hits"]})


def ask_the_platform(context: Any = None, question: str = "", account: str | None = None,
                     seed_synthetic: dict | None = None) -> dict:
    """Answer a platform question from certified KPIs in the observability database, with citations (or refuse)."""
    from altitude.observability.agent import AskThePlatform
    from altitude.observability.db import ObsDatabase

    ctx = coerce(context)
    db = ObsDatabase(str(ctx.workspace / "obs.duckdb"))
    try:
        seeded = None
        if seed_synthetic is not None and not db.relation_exists("SEMANTIC", "KPI_DEFINITIONS"):
            seeded = _seed_obs(db, seed_synthetic)
        ans = AskThePlatform(db, rubrics=ctx.rubrics, store=ctx.store).ask(question, account=account)
    finally:
        db.close()
    return safe({**ans.to_dict(), "seeded": seeded})


def _seed_obs(db: Any, seed: dict) -> dict:
    from altitude.observability.harvest import harvest_account
    from altitude.observability.kpi import compute_kpis
    from altitude.observability.sources import SyntheticSource
    from altitude.synthetic import AccountSpec

    kw = {k: seed[k] for k in ("account_name", "profile", "days") if k in seed}
    if seed.get("end_date"):
        kw["end_date"] = date.fromisoformat(seed["end_date"])
    spec = AccountSpec(**kw)
    res = harvest_account(db, SyntheticSource(spec, native_retention_days=spec.days), spec.end_date)
    counts = compute_kpis(db)
    return {"account_name": spec.account_name, "profile": spec.profile, "days": spec.days,
            "end_date": spec.end_date, "harvest_ok": res.ok, "kpis": len(counts)}


def run_agent(context: Any = None, agent_id: str = "", snapshot_id: str = "", as_of: str | None = None,
              tenant_id: str = "default", trigger: str = "manual", simulate: bool = True,
              require_promoted: bool = True, auto_execute: bool = True) -> dict:
    """Run one run-operations fleet agent on a sealed snapshot; L3 actions go to a simulated Snowflake executor."""
    from altitude.core.errors import AltitudeError
    from altitude_agents.executor import SimulatedSnowflake
    from altitude_agents.runtime import AgentRunner, registry
    from altitude_agents.telemetry import Telemetry

    ctx = coerce(context)
    if agent_id not in registry():
        raise SkillError(f"agent {agent_id!r} is not implemented; one of {sorted(registry())}")
    snap = open_snapshot(ctx, snapshot_id)
    tel = Telemetry.from_snapshot(snap)
    if as_of:
        tel = tel.at(datetime.fromisoformat(as_of))
    executor = SimulatedSnowflake(tel) if simulate else None
    try:
        report = AgentRunner(ctx.store, tenant_id=tenant_id, rubrics=ctx.rubrics).run(
            agent_id, tel, trigger=trigger, executor=executor, require_promoted=require_promoted,
            auto_execute=auto_execute)
    except AltitudeError as e:
        raise SkillError(str(e)) from None
    return safe({
        "run_id": report.run_id, "agent_id": report.agent_id, "version": report.version,
        "tenant_id": report.tenant_id, "telemetry_ref": report.telemetry_ref, "summary": report.summary,
        "tool_calls": report.tool_calls, "findings": len(report.findings),
        "findings_needing_review": sum(1 for f in report.findings if f["needs_review"]),
        "top_findings": [{k: f[k] for k in ("kind", "subject", "title", "confidence", "needs_review")}
                         for f in report.findings[:10]],
        "actions": [{"action_id": a.action_id, "action_type": a.action_type, "target": a.target,
                     "autonomy": a.autonomy, "status": a.status} for a in report.actions],
        "refused": report.refused, "incidents": [{"incident_id": i["incident_id"], "severity": i["severity"],
                                                  "title": i["title"]} for i in report.incidents],
        "executed_sql": list(getattr(executor, "executed", []) or []),
    })
