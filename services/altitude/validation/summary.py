"""Tier-level reconciliation summary for the go/no-go evidence pack (Section 13.2).

Per tier: objects, latest result per level, outstanding mismatches, accepted deviations (each
with approver and review-by date, flagged when expired) and open triage reviews. The summary is
derived only from ``validation_run`` / ``mismatch_cluster`` / ``accepted_deviation`` aggregates.
Readiness is evidence for the human go/no-go decision, never the decision itself.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from .config import LEVELS
from .deviation import deviations


def _latest_runs(store, engagement_id: str | None) -> list[dict]:
    sql = ("SELECT r.*, s.tier, s.engagement_id FROM validation_run r "
           "JOIN validation_suite s ON s.suite_id = r.suite_id")
    params: list = []
    if engagement_id:
        sql += " WHERE s.engagement_id = ?"
        params.append(engagement_id)
    sql += " ORDER BY r.completed_at, r.run_id"
    latest: dict[tuple, dict] = {}
    for r in store.query(sql, params):
        latest[(r["object_id"], r["level"])] = r
    return list(latest.values())


def tier_summary(store, as_of: date, engagement_id: str | None = None) -> dict:
    runs = _latest_runs(store, engagement_id)
    devs = deviations(store, as_of)
    active = {(d["object_id"], d["signature"]) for d in devs if not d["expired"]}
    run_ids = [r["run_id"] for r in runs]
    clusters: dict[str, list[dict]] = defaultdict(list)
    if run_ids:
        marks = ", ".join("?" for _ in run_ids)
        for c in store.query(f"SELECT * FROM mismatch_cluster WHERE run_id IN ({marks}) ORDER BY cluster_id",
                             run_ids):
            clusters[c["run_id"]].append(c)
    open_reviews = {r["subject_id"] for r in store.query(
        "SELECT subject_id FROM review_item WHERE status = 'open' AND subject_type = 'mismatch_cluster'")}

    tiers: dict[str, dict] = {}
    for r in sorted(runs, key=lambda x: (x["tier"], x["object_id"], x["level"])):
        t = tiers.setdefault(r["tier"], {
            "tier": r["tier"], "objects": set(), "levels": {lv: {"pass": 0, "fail": 0, "accepted_deviation": 0}
                                                           for lv in LEVELS},
            "outstanding_mismatches": 0, "failing": [], "open_triage_reviews": 0, "known_issues": set(),
        })
        t["objects"].add(r["object_id"])
        cl = clusters.get(r["run_id"], [])
        effective = r["result"]
        if effective == "fail" and cl and all((r["object_id"], c["signature"]) in active for c in cl):
            effective = "accepted_deviation"
        t["levels"][r["level"]][effective] += 1
        if effective == "fail":
            outstanding = sum(int(c["mismatch_count"]) for c in cl if (r["object_id"], c["signature"]) not in active)
            t["outstanding_mismatches"] += outstanding
            t["failing"].append({"object_id": r["object_id"], "level": r["level"], "run_id": r["run_id"],
                                 "clusters": [{"signature": c["signature"], "known_issue_id": c["known_issue_id"],
                                               "mismatch_count": int(c["mismatch_count"]),
                                               "confidence": float(c["confidence"])} for c in cl]})
        t["open_triage_reviews"] += sum(1 for c in cl if c["cluster_id"] in open_reviews)
        t["known_issues"].update(c["known_issue_id"] for c in cl if c["known_issue_id"])

    out_tiers = []
    for name in sorted(tiers):
        t = tiers[name]
        objs = t.pop("objects")
        tier_devs = [d for d in devs if d["object_id"] in objs]
        expired = [d for d in tier_devs if d["expired"]]
        reasons = []
        if t["failing"]:
            reasons.append(f"{len(t['failing'])} failing level result(s)")
        if expired:
            reasons.append(f"{len(expired)} accepted deviation(s) past review-by date")
        if t["open_triage_reviews"]:
            reasons.append(f"{t['open_triage_reviews']} triage cluster(s) awaiting human review")
        t.update({
            "objects": len(objs),
            "known_issues": sorted(t["known_issues"]),
            "accepted_deviations": [{
                "deviation_id": d["deviation_id"], "object_id": d["object_id"], "level": d["level"],
                "signature": d["signature"], "known_issue_id": d["known_issue_id"], "approver": d["approver"],
                "review_by": d["review_by"].isoformat(), "expired": d["expired"]} for d in tier_devs],
            "status": "ready" if not reasons else "not_ready",
            "reasons": reasons,
        })
        out_tiers.append(t)
    return {"as_of": as_of.isoformat(), "engagement_id": engagement_id, "tiers": out_tiers,
            "overall": "ready" if out_tiers and all(t["status"] == "ready" for t in out_tiers) else "not_ready"}


def render_md(summary: dict) -> str:
    lines = [f"# Reconciliation status by tier (as of {summary['as_of']})", "",
             f"Overall evidence status: **{summary['overall']}** (input to the go/no-go decision; "
             f"the decision itself requires a recorded approver).", ""]
    for t in summary["tiers"]:
        lines += [f"## {t['tier']} — {t['status']}", "",
                  f"Objects: {t['objects']} · outstanding mismatches: {t['outstanding_mismatches']} · "
                  f"open triage reviews: {t['open_triage_reviews']}", ""]
        if t["reasons"]:
            lines += [f"- {r}" for r in t["reasons"]] + [""]
        lines += ["| Level | Pass | Fail | Accepted deviation |", "|---|---|---|---|"]
        for lv, c in t["levels"].items():
            if sum(c.values()):
                lines.append(f"| {lv} | {c['pass']} | {c['fail']} | {c['accepted_deviation']} |")
        if t["failing"]:
            lines += ["", "Failing results:", ""]
            for f in t["failing"]:
                sigs = ", ".join(f"{c['signature']}→{c['known_issue_id'] or 'unmapped'} ({c['mismatch_count']})"
                                 for c in f["clusters"]) or "no root-cause cluster"
                lines.append(f"- {f['object_id']} {f['level']}: {sigs}")
        if t["accepted_deviations"]:
            lines += ["", "| Deviation | Object | Signature | Known issue | Approver | Review by |",
                      "|---|---|---|---|---|---|"]
            for d in t["accepted_deviations"]:
                flag = " (EXPIRED)" if d["expired"] else ""
                lines.append(f"| {d['deviation_id']} | {d['object_id']} | {d['signature']} | "
                             f"{d['known_issue_id'] or '—'} | {d['approver']} | {d['review_by']}{flag} |")
        lines.append("")
    return "\n".join(lines)
