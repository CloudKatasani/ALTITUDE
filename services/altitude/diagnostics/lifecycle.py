"""Persistence of diagnostic runs and the suggestion lifecycle.

    proposed → accepted → implemented → value_realised
         ↘ rejected   ↘ rejected     ↘ rejected

- Accepting or rejecting requires a named reviewer (principle 4); the reviewer is recorded on the
  suggestion and in the append-only ``diag_suggestion_event`` history and the audit trail.
- Suggestions below ``rubric.ai.review_confidence_min`` sit in the review queue
  (``altitude.core.ai.ReviewQueue``) and cannot be accepted until a reviewer approves them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from altitude.core import audit
from altitude.core.ai import ReviewQueue
from altitude.core.errors import ApprovalRequired
from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import Store, register_append_only

from .engine import DiagnosticResult, json_safe

register_append_only("diag_evidence", "diag_suggestion_event")

STATUSES = ("proposed", "accepted", "implemented", "value_realised", "rejected")
TRANSITIONS: dict[str, set[str]] = {
    "proposed": {"accepted", "rejected"},
    "accepted": {"implemented", "rejected"},
    "implemented": {"value_realised", "rejected"},
    "value_realised": set(),
    "rejected": set(),
}
REVIEWER_REQUIRED = {"accepted", "rejected"}
SUBJECT = "suggestion"


class LifecycleError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def run_id(result: DiagnosticResult) -> str:
    return stable_id("RUN", result.snapshot_id, result.rubric_version, result.catalogue_hash, result.tier)


def persist(result: DiagnosticResult, store: Store, *, tenant_id: str | None = None, engagement_id: str | None = None,
            rubrics: RubricSet | None = None, snapshot: Any = None) -> str:
    """Record a run, its evidence, suggestions (+ AI inferences / review queue) and scores. Idempotent."""
    rubrics = rubrics or default_rubrics()
    rid = run_id(result)
    now = _now()
    if snapshot is not None:
        snapshot.register(store)
    if not store.get("diag_run", run_id=rid):
        store.insert("diag_run", {
            "run_id": rid, "snapshot_id": result.snapshot_id, "rubric_version": result.rubric_version,
            "catalogue_hash": result.catalogue_hash, "tier": result.tier, "tenant_id": tenant_id,
            "engagement_id": engagement_id, "platform_health_index": result.scorecard["platform_health_index"],
            "suggestions": len(result.details),
            "summary": json_safe({"scorecard": {k: v for k, v in result.scorecard.items() if k != "checks"},
                                  "recommendations": result.recommendations}),
            "created_at": now,
        })
        rows = []
        for d in result.scorecard["domains"]:
            rows.append({"run_id": rid, "scope": "domain", "scope_key": d["id"], "score": d["score"], "raw": d["raw"],
                         "label": d["label"]})
        for p in result.scorecard["pillars"]:
            rows.append({"run_id": rid, "scope": "pillar", "scope_key": p["pillar"], "score": p["score"],
                         "raw": p["raw"], "label": p["label"]})
        phi = result.scorecard["platform_health_index"]
        rows.append({"run_id": rid, "scope": "phi", "scope_key": "PHI", "score": None,
                     "raw": None if phi is None else round(phi / 100.0, 4), "label": None})
        store.insert("diag_score", rows)

    existing_ev = {r["evidence_id"] for r in store.query(
        "SELECT evidence_id FROM diag_evidence WHERE snapshot_id = ?", [result.snapshot_id])}
    new_ev = [{
        "evidence_id": e["id"], "snapshot_id": e["snapshot_id"], "check_id": e["check_id"], "object_name": e["object"],
        "kind": e["kind"], "cluster_key": e["cluster_key"], "metrics": e["metrics"], "detector_ref": e["detector_ref"],
        "detector_sha": e["detector_sha"], "created_at": now,
    } for e in result.evidence if e["id"] not in existing_ev]
    store.insert("diag_evidence", new_ev)

    queue = ReviewQueue(store, rubrics)
    for d in result.details:
        rec = d.record
        if store.get("diag_suggestion", suggestion_id=rec["id"]):
            continue
        value = rec["value"]["annualised_usd"] or {}
        store.insert("diag_suggestion", {
            "suggestion_id": rec["id"], "run_id": rid, "snapshot_id": rec["snapshot_id"],
            "rubric_version": result.rubric_version, "check_id": rec["check_id"], "domain": rec["domain"],
            "waf_pillar": rec["waf_pillar"], "title": rec["title"], "record": rec,
            "value_p50_usd": value.get("p50"), "value_conservative_usd": value.get("conservative"),
            "risk_score": (rec["risk_reduction"] or {}).get("score"), "confidence": rec["confidence"],
            "needs_review": d.needs_review, "quadrant": rec["priority"]["quadrant"],
            "priority_rank": rec["priority"]["rank"], "status": "proposed", "reviewer": None,
            "narrative": d.narrative, "created_at": now, "updated_at": now,
        })
        store.insert("diag_suggestion_event", {
            "event_id": f"DSE-{uuid.uuid4().hex[:12].upper()}", "suggestion_id": rec["id"], "from_status": None,
            "to_status": "proposed", "actor": "altitude-diagnostics", "reviewer": None,
            "comment": f"published from {result.snapshot_id} ({result.rubric_version})", "occurred_at": now,
        })
        inf = d.inference
        inf.tenant_id = tenant_id
        queue.record(inf, sample=True)
    return rid


def get(store: Store, suggestion_id: str) -> dict:
    row = store.get("diag_suggestion", suggestion_id=suggestion_id)
    if row is None:
        raise KeyError(f"unknown suggestion {suggestion_id}")
    return row


def review(store: Store, suggestion_id: str, reviewer: str, decision: str, comment: str | None = None,
           rubrics: RubricSet | None = None) -> None:
    """Decide the open review-queue item(s) for a suggestion (approved | rejected | modified)."""
    if not reviewer:
        raise ApprovalRequired("a named reviewer is required to decide a review item")
    get(store, suggestion_id)
    queue = ReviewQueue(store, rubrics or default_rubrics())
    items = [i for i in queue.open_items(SUBJECT) if i["subject_id"] == suggestion_id]
    if not items:
        raise LifecycleError(f"{suggestion_id} has no open review item")
    for item in items:
        queue.decide(item["item_id"], reviewer, decision, comment)
    audit.record(store, reviewer, f"review.{decision}", subject_type=SUBJECT, subject_id=suggestion_id,
                 details={"comment": comment})


def in_review_queue(store: Store, suggestion_id: str) -> bool:
    rows = store.query("SELECT 1 FROM review_item WHERE subject_type = ? AND subject_id = ? AND status = 'open'",
                       [SUBJECT, suggestion_id])
    return bool(rows)


def transition(store: Store, suggestion_id: str, to_status: str, *, actor: str, reviewer: str | None = None,
               comment: str | None = None, rubrics: RubricSet | None = None) -> dict:
    if to_status not in STATUSES:
        raise LifecycleError(f"unknown status {to_status!r}")
    row = get(store, suggestion_id)
    current = row["status"]
    if to_status not in TRANSITIONS[current]:
        raise LifecycleError(f"{suggestion_id}: {current} → {to_status} is not a valid transition")
    if to_status in REVIEWER_REQUIRED and not reviewer:
        raise ApprovalRequired(f"{suggestion_id}: marking a suggestion {to_status} requires a named reviewer")
    if not actor:
        raise ApprovalRequired("every lifecycle transition records an actor")
    queue = ReviewQueue(store, rubrics or default_rubrics())
    if to_status == "accepted":
        if in_review_queue(store, suggestion_id) or not queue.is_cleared(SUBJECT, suggestion_id):
            raise ApprovalRequired(
                f"{suggestion_id} is in the review queue (confidence {float(row['confidence']):.2f}); "
                "a reviewer must approve it before it can be accepted")
    new_reviewer = reviewer or row.get("reviewer")
    record = row["record"]
    if isinstance(record, str):
        import json

        record = json.loads(record)
    record = {**record, "status": to_status, "reviewer": new_reviewer}
    now = _now()
    store.update("diag_suggestion", {"suggestion_id": suggestion_id},
                 {"status": to_status, "reviewer": new_reviewer, "record": record, "updated_at": now})
    store.insert("diag_suggestion_event", {
        "event_id": f"DSE-{uuid.uuid4().hex[:12].upper()}", "suggestion_id": suggestion_id, "from_status": current,
        "to_status": to_status, "actor": actor, "reviewer": reviewer, "comment": comment, "occurred_at": now,
    })
    audit.record(store, actor, f"suggestion.{to_status}", subject_type=SUBJECT, subject_id=suggestion_id,
                 details={"from": current, "reviewer": reviewer, "comment": comment})
    return get(store, suggestion_id)


def accept(store: Store, suggestion_id: str, reviewer: str | None, comment: str | None = None, **kw: Any) -> dict:
    return transition(store, suggestion_id, "accepted", actor=reviewer or "", reviewer=reviewer, comment=comment, **kw)


def reject(store: Store, suggestion_id: str, reviewer: str | None, comment: str | None = None, **kw: Any) -> dict:
    return transition(store, suggestion_id, "rejected", actor=reviewer or "", reviewer=reviewer, comment=comment, **kw)


def history(store: Store, suggestion_id: str) -> list[dict]:
    return store.query("SELECT * FROM diag_suggestion_event WHERE suggestion_id = ? ORDER BY occurred_at, event_id",
                       [suggestion_id])


def statuses(store: Store, snapshot_id: str | None = None) -> list[dict]:
    sql = ("SELECT suggestion_id, snapshot_id, check_id, title, status, reviewer, confidence, needs_review, quadrant, "
           "priority_rank FROM diag_suggestion")
    params: list = []
    if snapshot_id:
        sql += " WHERE snapshot_id = ?"
        params.append(snapshot_id)
    return store.query(sql + " ORDER BY snapshot_id, priority_rank", params)


def overlay_status(result: DiagnosticResult, store: Store | None) -> list[dict]:
    """Canonical records with lifecycle status/reviewer taken from the store (when one is given)."""
    if store is None:
        return [dict(s) for s in result.suggestions]
    current = {r["suggestion_id"]: r for r in statuses(store, result.snapshot_id)}
    out = []
    for s in result.suggestions:
        row = current.get(s["id"])
        out.append({**s, "status": row["status"], "reviewer": row["reviewer"]} if row else dict(s))
    return out
