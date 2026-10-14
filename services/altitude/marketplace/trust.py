"""Evidence-based certification of data products and readiness of marketplace agents.

Runs against a sealed estate snapshot (harvest contract tables). Weights, the certification bar and blocking
checks come from ``rubric.marketplace``. Each failing check names the Package D check that remediates it.
"""

from __future__ import annotations

import json
from datetime import time
from typing import Any

from altitude.core.ids import content_hash
from altitude.core.rubric import RubricSet, default_rubrics

from .catalog import agents as agent_manifests
from .catalog import products as product_manifests

FIX = {  # failing check -> Package D check that remediates it
    "owner": "DX-GOV-01", "documentation": "DX-AI-03", "quality_monitors": "DX-GOV-02", "privacy": "DX-SEC-05",
    "freshness": "DX-REL-02", "budget": "DX-AI-02", "semantic_layer": "DX-AI-01",
}


def _split(fq: str) -> tuple[str, str, str]:
    db, sch, name = fq.split(".")
    return db, sch, name


def _check(key: str, passed: bool, detail: str, weight: float = 0.0, blocking: bool = False) -> dict:
    return {"check": key, "passed": bool(passed), "detail": detail, "weight": weight, "blocking": blocking,
            "fix": None if passed else FIX.get(key)}


def _product(snap: Any, p: dict, rs: RubricSet) -> dict:
    w = rs.get("rubric.marketplace.product_weights")
    blocking = set(rs.get("rubric.marketplace.blocking"))
    tables = [o["table"] for o in p["objects"]]
    existing = {r["FQ_NAME"]: r for r in snap.query(
        "SELECT FQ_NAME, COMMENT FROM TABLES WHERE list_contains(?, FQ_NAME)", [tables])}
    missing = [t for t in tables if t not in existing]
    cols = {(r["FQ_NAME"], r["COLUMN_NAME"]): r["COMMENT"] for r in snap.query(
        "SELECT FQ_NAME, COLUMN_NAME, COMMENT FROM COLUMNS WHERE list_contains(?, FQ_NAME)", [tables])}
    declared = [(o["table"], c) for o in p["objects"] for c in o["columns"]]
    absent = [f"{t}.{c}" for t, c in declared if (t, c) not in cols]
    owners = {f"{r['OBJECT_DATABASE']}.{r['OBJECT_SCHEMA']}.{r['OBJECT_NAME']}" for r in snap.query(
        "SELECT OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME FROM TAG_REFERENCES "
        "WHERE upper(TAG_NAME) = 'DATA_OWNER' AND COLUMN_NAME IS NULL")}
    no_owner = [t for t in tables if t not in owners]
    described = [k for k in declared if cols.get(k)]
    col_share = len(described) / len(declared) if declared else 1.0
    undocumented_tables = [t for t in tables if t in existing and not existing[t]["COMMENT"]]
    dmf = {r["REF_ENTITY_NAME"] for r in snap.query("SELECT REF_ENTITY_NAME FROM DATA_METRIC_FUNCTION_REFERENCES")}
    no_dmf = [t for t in tables if t not in dmf]
    pii = [(f"{r['OBJECT_DATABASE']}.{r['OBJECT_SCHEMA']}.{r['OBJECT_NAME']}", r["COLUMN_NAME"]) for r in snap.query(
        "SELECT OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, COLUMN_NAME FROM TAG_REFERENCES "
        "WHERE upper(TAG_NAME) = 'PII' AND COLUMN_NAME IS NOT NULL")]
    masked = {(f"{r['REF_DATABASE_NAME']}.{r['REF_SCHEMA_NAME']}.{r['REF_ENTITY_NAME']}", r["REF_COLUMN_NAME"])
              for r in snap.query("SELECT REF_DATABASE_NAME, REF_SCHEMA_NAME, REF_ENTITY_NAME, REF_COLUMN_NAME "
                                  "FROM POLICY_REFERENCES WHERE POLICY_KIND = 'MASKING_POLICY'")}
    exposed_pii = [f"{t}.{c}" for t, c in pii if (t, c) in set(declared) and (t, c) not in masked]
    checks = [
        _check("exists", not missing, "all objects exist" if not missing else f"missing: {', '.join(missing)}",
               w["exists"], "exists" in blocking),
        _check("contract", not absent, f"{len(declared)} contract columns present" if not absent
               else f"columns not found: {', '.join(absent)}", w["contract"], "contract" in blocking),
        _check("owner", not no_owner, "owner tag on every object" if not no_owner
               else f"no DATA_OWNER tag: {', '.join(no_owner)}", w["owner"], "owner" in blocking),
        _check("documentation",
               not undocumented_tables and col_share >= float(rs.get("rubric.marketplace.column_comment_min")),
               f"{col_share:.0%} of exposed columns described"
               + (f"; no table comment on {', '.join(undocumented_tables)}" if undocumented_tables else ""),
               w["documentation"], "documentation" in blocking),
        _check("quality_monitors", not no_dmf, "data metric functions on every object" if not no_dmf
               else f"no DMFs on: {', '.join(no_dmf)}", w["quality_monitors"], "quality_monitors" in blocking),
        _check("privacy", not exposed_pii, "every PII column exposed is masked" if not exposed_pii
               else f"PII exposed without masking: {', '.join(exposed_pii)}", w["privacy"], "privacy" in blocking),
    ]
    if p.get("freshness"):
        f = p["freshness"]
        hh, mm = (int(x) for x in f["deadline_utc"].split(":"))
        runs = snap.query("SELECT CAST(SCHEDULED_TIME AS DATE) AS D, max(COMPLETED_TIME) AS DONE, "
                          "bool_or(STATE = 'SUCCEEDED') AS OK FROM TASK_HISTORY WHERE FQ_NAME = ? GROUP BY 1",
                          [f["loaded_by"]])
        on_time = [r for r in runs if r["OK"] and r["DONE"] and r["DONE"].time() <= time(hh, mm)]
        share = len(on_time) / len(runs) if runs else 0.0
        checks.append(_check("freshness", share >= float(rs.get("rubric.marketplace.freshness_on_time_min")),
                             f"loaded by {f['deadline_utc']} UTC on {share:.0%} of {len(runs)} days",
                             w["freshness"], "freshness" in blocking))
    applicable = sum(c["weight"] for c in checks)
    score = round(sum(c["weight"] for c in checks if c["passed"]) / applicable, 3) if applicable else 0.0
    blockers = [c["check"] for c in checks if c["blocking"] and not c["passed"]]
    certified = score >= float(rs.get("rubric.marketplace.certify_min_score")) and not blockers
    consumers = snap.scalar(
        "SELECT count(DISTINCT USER_NAME) FROM ACCESS_HISTORY WHERE list_contains(?, OBJECT_NAME) "
        "AND QUERY_START_TIME >= (SELECT max(QUERY_START_TIME) FROM ACCESS_HISTORY) - to_days(?)",
        [tables, int(rs.get("rubric.marketplace.adoption_window_days"))]) or 0
    return {"id": p["id"], "name": p["name"], "domain": p["domain"], "owner": p["owner"],
            "classification": p["classification"], "score": score, "certified": certified, "blockers": blockers,
            "status": "certified" if certified else "blocked", "checks": checks, "consumers": int(consumers),
            "fixes": sorted({c["fix"] for c in checks if c["fix"]})}


def _agent(snap: Any, a: dict, product_status: dict[str, dict], rs: RubricSet, package_o: bool) -> dict:
    roles = {r["NAME"] for r in snap.query("SELECT NAME FROM ROLES")}
    budgets = snap.query("SELECT SCOPE, OBJECTS FROM BUDGETS")
    has_budget = any(b["SCOPE"] == "CORTEX" or (b["OBJECTS"] or "").find(a["role"]) >= 0 for b in budgets)
    if a["kind"] == "cortex_search":
        db, sch, name = _split(a["search_service"])
        layer = bool(snap.query("SELECT 1 FROM CORTEX_SEARCH_SERVICES WHERE DATABASE_NAME=? AND SCHEMA_NAME=? AND NAME=?",
                                [db, sch, name]))
        layer_detail = f"search service {a['search_service']}"
    elif a.get("provided_by") == "package_o":
        layer = package_o
        layer_detail = f"semantic view {a['semantic_view']} (deployed with Package O)"
    else:
        db, sch, name = _split(a["semantic_view"])
        layer = bool(snap.query("SELECT 1 FROM SEMANTIC_VIEWS WHERE DATABASE_NAME=? AND SCHEMA_NAME=? AND NAME=?",
                                [db, sch, name]))
        layer_detail = f"semantic view {a['semantic_view']}"
    not_certified = [d for d in a["products"] if not product_status.get(d, {}).get("certified")]
    min_q = int(rs.get("rubric.marketplace.agent_golden_questions_min"))
    checks = [
        _check("products", not not_certified, "all data products certified" if not not_certified
               else f"waiting on: {', '.join(not_certified)}"),
        _check("role", a["role"] in roles and a["role"] not in ("ACCOUNTADMIN", "SYSADMIN", "PUBLIC"),
               f"runs as dedicated role {a['role']}"),
        _check("budget", has_budget, "Cortex spend budget in place" if has_budget else "no Cortex budget for the agent role"),
        _check("semantic_layer", layer, layer_detail + (" exists" if layer else " not deployed")),
        _check("evaluation", a["golden_questions"] >= min_q,
               f"{a['golden_questions']} golden questions (minimum {min_q})"),
    ]
    ready = all(c["passed"] for c in checks)
    return {"id": a["id"], "name": a["name"], "kind": a["kind"], "products": a["products"], "ready": ready,
            "status": "ready" if ready else "blocked", "checks": checks,
            "fixes": sorted({c["fix"] for c in checks if c["fix"]})}


def assess(snapshot: Any, rubrics: RubricSet | None = None, package_o: bool = False) -> dict:
    """Certify every product and check every agent against one sealed snapshot (reproducible)."""
    rs = rubrics or default_rubrics()
    prods = [_product(snapshot, p, rs) for p in product_manifests()]
    by_id = {p["id"]: p for p in prods}
    agents = [_agent(snapshot, a, by_id, rs, package_o) for a in agent_manifests()]
    out = {"snapshot_id": getattr(snapshot, "snapshot_id", "adhoc"), "rubric_version": rs.version,
           "products": prods, "agents": agents,
           "summary": {"products": len(prods), "certified": sum(p["certified"] for p in prods),
                       "agents": len(agents), "ready": sum(a["ready"] for a in agents)}}
    out["assessment_hash"] = content_hash(json.loads(json.dumps(out, default=str)), 16)
    return out
