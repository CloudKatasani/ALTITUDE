"""Go/no-go evidence pack (Section 13.2), generated from snapshots and the canonical model."""

from __future__ import annotations

import json
import operator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from altitude.core import audit
from altitude.core.errors import ApprovalRequired
from altitude.core.ids import content_hash, stable_id
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.theme import render

_OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt, "<": operator.lt}


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) and v[:1] in "[{" else v


def evaluate_criteria(metrics: dict, rubrics: RubricSet | None = None) -> list[dict]:
    rubrics = rubrics or default_rubrics()
    out = []
    for c in load_yaml("cutover/go_no_go.yaml")["criteria"]:
        target = rubrics.get(c["ref"]) if "ref" in c else c["value"]
        actual = metrics.get(c["metric"])
        passed = actual is not None and _OPS[c["op"]](actual, target)
        out.append({"metric": c["metric"], "op": c["op"], "target": target, "actual": actual, "passed": bool(passed),
                    "target_ref": c.get("ref")})
    return out


def _reconciliation(store: Any, engagement_id: str) -> dict:
    runs = store.query(
        "SELECT r.*, s.tier FROM validation_run r JOIN validation_suite s ON r.suite_id = s.suite_id "
        "WHERE s.engagement_id = ? ORDER BY r.object_id, r.level", [engagement_id])
    accepted = {r["run_id"] for r in store.query(
        "SELECT a.run_id FROM accepted_deviation a JOIN validation_run r ON a.run_id = r.run_id")}
    by_tier: dict[str, dict] = {}
    unaccepted_t1 = 0
    perf_breaches = 0
    for r in runs:
        t = by_tier.setdefault(r["tier"], {"runs": 0, "pass": 0, "fail": 0, "accepted_deviation": 0})
        t["runs"] += 1
        result = "accepted_deviation" if (r["result"] == "fail" and r["run_id"] in accepted) else r["result"]
        t[result] = t.get(result, 0) + 1
        if r["tier"] == "tier1" and r["level"] == "L3" and result == "fail":
            unaccepted_t1 += 1
        if r["level"] == "L5" and result == "fail":
            perf_breaches += 1
    return {"by_tier": by_tier, "tier1_l3_unaccepted": unaccepted_t1, "performance_breaches": perf_breaches,
            "evidence_refs": [r["run_id"] for r in runs]}


def _security(store: Any, engagement_id: str) -> dict:
    rows = store.query(
        "SELECT g.mapping_status FROM \"grant\" g JOIN source_system s ON g.source_system_id = s.source_system_id "
        "WHERE s.engagement_id = ?", [engagement_id])
    total = len(rows)
    mapped = sum(1 for r in rows if r["mapping_status"] in ("mapped", "retired", "intentionally_retired"))
    return {"legacy_grants": total, "mapped_or_retired": mapped,
            "grants_mapped_pct": round(100.0 * mapped / total, 2) if total else 100.0}


def _rollback(store: Any, plan_id: str) -> dict:
    plans = store.query("SELECT * FROM rollback_plan WHERE plan_id = ?", [plan_id])
    rehearsals = store.query("SELECT * FROM rehearsal WHERE plan_id = ? ORDER BY executed_at", [plan_id])
    rehearsed = any(p["rehearsed"] for p in plans) and any(r["result"] == "success" for r in rehearsals)
    return {"plans": [p["rollback_id"] for p in plans], "rehearsals": [
        {"id": r["rehearsal_id"], "result": r["result"], "at": str(r["executed_at"])} for r in rehearsals],
        "rehearsed": rehearsed}


def build_go_no_go_pack(store: Any, engagement_id: str, plan_id: str, snapshot_id: str, facts: dict | None = None,
                        rubrics: RubricSet | None = None) -> dict:
    """Assemble the pack. ``facts`` carries operational evidence not held in the model:
    ``parallel_cycles`` (list of {date, clean, month_end}), ``uat_signoffs`` ({area: signer|None}),
    ``open_defects`` ({S1: n, ...}), ``runbook_ready``, ``on_call_ready``, ``agent_fleet_healthy``.
    """
    rubrics = rubrics or default_rubrics()
    facts = facts or {}
    plan = store.get("cutover_plan", plan_id=plan_id)
    if plan is None:
        raise KeyError(f"no cutover plan {plan_id}")
    recon = _reconciliation(store, engagement_id)
    sec = _security(store, engagement_id)
    rb = _rollback(store, plan_id)
    cycles = facts.get("parallel_cycles", [])
    consecutive = 0
    month_end_seen = False
    for c in reversed(cycles):
        if not c.get("clean"):
            break
        consecutive += 1
        month_end_seen = month_end_seen or bool(c.get("month_end"))
    # a clean streak only counts once it includes a month-end cycle (when the rubric requires one)
    month_end_required = rubrics.get("rubric.cutover.month_end_cycle_required")
    clean_cycles = consecutive if (month_end_seen or not month_end_required) else 0
    signoffs = facts.get("uat_signoffs", {})
    defects = facts.get("open_defects", {})
    metrics = {
        "tier1_l3_mismatches_unaccepted": recon["tier1_l3_unaccepted"],
        "consecutive_clean_parallel_cycles": clean_cycles,
        "rollback_rehearsed": rb["rehearsed"],
        "grants_mapped_pct": sec["grants_mapped_pct"],
        "open_s1_defects": int(defects.get("S1", 0)),
        "uat_signoffs_missing": sum(1 for v in signoffs.values() if not v),
        "performance_sla_breaches": recon["performance_breaches"],
    }
    criteria = evaluate_criteria(metrics, rubrics)
    recommendation = "go" if all(c["passed"] for c in criteria) else "no_go"
    pack = {
        "engagement_id": engagement_id, "plan_id": plan_id, "strategy": plan["strategy"], "scope": plan["scope"],
        "snapshot_id": snapshot_id, "rubric_version": rubrics.version,
        "sections": {
            "reconciliation": recon,
            "performance": {"breaches": recon["performance_breaches"]},
            "security": sec,
            "operations": {k: facts.get(k) for k in ("runbook_ready", "on_call_ready", "agent_fleet_healthy")},
            "rollback": rb,
            "business": {"uat_signoffs": signoffs, "open_defects": defects,
                         "parallel_cycles": cycles, "month_end_cycle_seen": month_end_seen},
        },
        "metrics": metrics, "criteria": criteria, "recommendation": recommendation,
    }
    pack["pack_hash"] = content_hash(pack, 24)
    gid = stable_id("GNG", plan_id, snapshot_id, pack["pack_hash"])
    if not store.get("go_no_go", go_no_go_id=gid):
        store.insert("go_no_go", {"go_no_go_id": gid, "plan_id": plan_id, "snapshot_id": snapshot_id,
                                  "evidence_pack": pack, "recommendation": recommendation})
    pack["go_no_go_id"] = gid
    return pack


def decide(store: Any, go_no_go_id: str, decided_by: str, decision: str, override_reason: str | None = None) -> None:
    """Record the human go/no-go decision. Overriding a no_go recommendation needs a written reason."""
    if not decided_by:
        raise ApprovalRequired("go/no-go needs a named decision maker")
    row = store.get("go_no_go", go_no_go_id=go_no_go_id)
    if row is None:
        raise KeyError(go_no_go_id)
    if decision not in ("go", "no_go"):
        raise ValueError("decision must be go or no_go")
    if decision == "go" and row["recommendation"] != "go" and not override_reason:
        raise ApprovalRequired("overriding a no_go recommendation requires an override reason")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    store.update("go_no_go", {"go_no_go_id": go_no_go_id}, {"decision": decision, "decided_by": decided_by,
                                                            "decided_at": now})
    audit.record(store, decided_by, f"cutover.{decision}", subject_type="go_no_go", subject_id=go_no_go_id,
                 details={"override_reason": override_reason} if override_reason else None)


def render_markdown(pack: dict, theme: str | None = None) -> str:
    env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), autoescape=False)
    layout = load_yaml("cutover/go_no_go.yaml")["sections"]
    return render(env.get_template("go_no_go.md.j2").render(pack=pack, layout=layout), theme)
