"""Live samples for the website, all computed from one synthetic estate (clearly labelled as synthetic)."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path
from typing import Any

from altitude.core.snapshot import Snapshot
from altitude.core.store import json_safe

DRIFT_SAMPLE = {
    "teradata": """CREATE SET TABLE edw.customer_dim (
  cust_id INTEGER, cust_name VARCHAR(100) NOT CASESPECIFIC, region CHAR(10)
);
SELECT region, total_sales / order_count AS avg_order
FROM edw.sales_summary
WHERE cust_name = 'ACME';
.IF ERRORCODE <> 0 THEN .GOTO fail;""",
    "oracle": """SELECT NVL(email, 'n/a') AS email, amount
FROM customers c, orders o
WHERE c.id = o.customer_id(+)
  AND c.notes IS NULL;""",
}


def _snapshot(cache: Path, profile: str = "seeded") -> Snapshot:
    from altitude.synthetic import AccountSpec, build_snapshot

    sid = f"SNAP-ACME-2026-09-30-{profile.upper()}-SITE"
    path = cache / f"{sid}.duckdb"
    if path.exists():
        return Snapshot.open(path)
    snap, _ = build_snapshot(cache, AccountSpec(profile=profile), snapshot_id=sid)
    return snap


def collect(cache_dir: str | Path, assets_dir: str | Path | None = None) -> dict[str, Any]:
    """Compute every sample. ``assets_dir`` receives downloadable sample artefacts (report, dashboards)."""
    from altitude.airready.scoring import score as ai_score
    from altitude.diagnostics.engine import run as diag_run
    from altitude.diagnostics.exports import export_all
    from altitude.foundation.wa import run as wa_run
    from altitude.patterns import scan_sql
    from altitude.patterns.library import default_library
    from altitude_agents.catalogue import load_agent_catalogue

    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    snap = _snapshot(cache)
    result = diag_run(snap, tier="D2")
    sugg = sorted(result.suggestions, key=lambda s: s["priority"]["rank"])
    evidence = {e["id"]: e for e in result.evidence}
    wa = wa_run(snap)
    ai = ai_score(snap)
    lib = default_library()
    by_dialect: dict[str, int] = {}
    s1: dict[str, int] = {}
    for i in lib.issues.values():
        by_dialect[i.source_dialect] = by_dialect.get(i.source_dialect, 0) + 1
        if i.severity == "S1":
            s1[i.source_dialect] = s1.get(i.source_dialect, 0) + 1
    drift = {d: [{"issue_id": h.issue_id, "severity": h.severity, "line": h.line, "message": h.message}
                 for h in scan_sql(sql, d)] for d, sql in DRIFT_SAMPLE.items()}
    agents = sorted(load_agent_catalogue().values(), key=lambda a: a.number)
    value = sum(float((s["value"]["annualised_usd"] or {}).get("p50") or 0) for s in sugg)
    out: dict[str, Any] = {
        "snapshot_id": snap.snapshot_id, "snapshot_hash": snap.content_hash,
        "window": [result.context.window_start.date().isoformat(), result.context.window_end.date().isoformat()],
        "phi": result.scorecard["platform_health_index"],
        "domains": result.scorecard["domains"], "pillars": result.scorecard["pillars"],
        "suggestions": len(sugg), "value_p50": round(value, 2),
        "quick_wins": [s for s in sugg if s["priority"]["quadrant"] == "quick_win"],
        "top": [{**s, "evidence": [evidence[r] for r in s["evidence_refs"][:2] if r in evidence]} for s in sugg[:10]],
        "quadrants": {q: sum(1 for s in sugg if s["priority"]["quadrant"] == q)
                      for q in ("quick_win", "strategic", "hygiene", "defer")},
        "wa": {"overall": wa.overall, "rating": wa.rating, "findings": len(wa.findings),
               "pillars": wa.waf_pillar_scores},
        "ai": {"overall": ai.overall, "level": ai.maturity_level, "label": ai.maturity_label,
               "pillars": {k: v["score"] for k, v in ai.pillars.items()}},
        "patterns": {"issues": len(lib.issues), "mappings": len(lib.mappings), "tests": len(lib.tests),
                     "by_dialect": dict(sorted(by_dialect.items())), "s1_by_dialect": dict(sorted(s1.items()))},
        "drift": drift, "drift_sql": DRIFT_SAMPLE,
        "agents": [{"name": a.name, "id": a.agent_id, "trigger": a.trigger.get("description", ""),
                    "purpose": a.purpose, "autonomy": a.max_autonomy, "kpi": a.kpi, "live": a.implemented}
                   for a in agents],
    }
    out["observability"] = _observability(cache, assets_dir)
    out["marketplace"] = _marketplace(cache, snap)
    if assets_dir is not None:
        assets = Path(assets_dir)
        tmp = cache / "diag_exports"
        export_all(result, tmp, formats=["report_html", "findings_csv"])
        (assets / "samples").mkdir(parents=True, exist_ok=True)
        shutil.copy(tmp / "diagnostic_report.html", assets / "samples" / "diagnostic_report.html")
        shutil.copy(tmp / "findings_register.csv", assets / "samples" / "findings_register.csv")
    return json_safe(out)


def _observability(cache: Path, assets_dir: str | Path | None) -> dict:
    from altitude.observability.agent import AskThePlatform
    from altitude.observability.alerts import alert_history, evaluate_alerts
    from altitude.observability.dashboards import render_dashboards
    from altitude.observability.db import ObsDatabase
    from altitude.observability.harvest import harvest_registry
    from altitude.observability.kpi import compute_kpis, implemented

    as_of = date(2026, 9, 30)
    db_path = cache / "obs_site.duckdb"
    fresh = not db_path.exists()
    db = ObsDatabase(str(db_path))
    reg = {"tenant_id": "SITE", "tenant_name": "Synthetic sample", "central_account": "ACME_PROD",
           "accounts": [{"account_name": "ACME_PROD", "environment": "prod", "source": "synthetic",
                         "synthetic": {"organization": "ACME", "profile": "seeded", "seed": 7,
                                       "anomalies": [{"date": "2026-09-29", "warehouse": "WH_DS", "factor": 3}]}}],
           "alert_routes": {r: {"channel": "slack", "target": f"#{r}"} for r in
                            ("finops", "dataops", "security", "platform", "governance", "ai")}}
    if fresh:
        harvest_registry(db, reg, as_of, days=60)
        compute_kpis(db)
    kpis = implemented()
    if fresh:
        evaluate_alerts(db, reg, as_of, None)
        evaluate_alerts(db, reg, date(2026, 9, 29), None)
    alerts = sorted(alert_history(db), key=lambda a: (str(a.get("SEVERITY")) != "high", str(a.get("ALERT_ID"))))
    ask = AskThePlatform(db).ask("What is the idle credit share by warehouse?")
    if assets_dir is not None:
        out = Path(assets_dir) / "samples" / "observability"
        render_dashboards(db, out, as_of=as_of, registry=reg)
    tiers: dict[str, int] = {}
    domains: dict[str, int] = {}
    for k in kpis:
        tiers[k.get("tier", "core")] = tiers.get(k.get("tier", "core"), 0) + 1
        domains[k.get("domain", "other")] = domains.get(k.get("domain", "other"), 0) + 1
    return {"kpis_implemented": len(kpis), "kpi_tiers": tiers, "kpi_domains": domains,
            "alerts": _dedupe_alerts(alerts)[:8],
            "ask": {"question": ask.question, "answer": ask.text,
                    "citations": [c["kpi_id"] for c in ask.citations]}}


def _dedupe_alerts(alerts: list[dict]) -> list[dict]:
    """One row per (alert, object): the latest firing, with how many days it fired."""
    seen: dict[tuple, dict] = {}
    for a in alerts:
        key = (a["ALERT_ID"], a.get("DIMENSION"))
        row = seen.setdefault(key, {"alert": a["ALERT_ID"], "object": a.get("DIMENSION"), "severity": a["SEVERITY"],
                                    "route": a["ROUTE"], "runbook": a["RUNBOOK"], "days": 0})
        row["days"] += 1
    return list(seen.values())


def _marketplace(cache: Path, seeded: Snapshot) -> dict:
    """Certification of the sample products and agents before (seeded) and after remediation (clean estate)."""
    from altitude.marketplace import agents, assess, products

    before = assess(seeded, package_o=True)
    after = assess(_snapshot(cache, "clean"), package_o=True)
    a_by = {x["id"]: x for x in after["products"]}
    ag_after = {x["id"]: x for x in after["agents"]}
    manifests = {p["id"]: p for p in products()}
    agent_manifests = {a["id"]: a for a in agents()}
    return {
        "summary_before": before["summary"], "summary_after": after["summary"],
        "products": [{**manifests[p["id"]], "before": p, "after": a_by[p["id"]]} for p in before["products"]],
        "agents": [{**agent_manifests[a["id"]], "before": a, "after": ag_after[a["id"]]} for a in before["agents"]],
    }
