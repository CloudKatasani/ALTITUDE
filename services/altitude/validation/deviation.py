"""Accepted-deviation workflow: a data owner signs off a known mismatch until a review-by date.

Rules (Sections 12.3, 13.2, principle 4):
- only the object's registered data owner may accept a deviation (recorded approver);
- every deviation carries a review-by date in the future and within
  ``rubric.validation.deviation.review_by_max_days``;
- acceptance is recorded in ``accepted_deviation`` (+ scope), ``approval`` and the audit trail;
- runs on or before the review-by date with the same object + signature are classified
  ``accepted_deviation``; afterwards they fail again until re-approved.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from altitude.core import audit
from altitude.core.errors import ApprovalRequired
from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics


def assign_data_owner(store, object_id: str, data_owner: str, assigned_by: str, now: datetime | None = None) -> None:
    if not data_owner or not assigned_by:
        raise ApprovalRequired("a named data owner and assigner are required")
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    existing = store.get("validation_object_owner", object_id=object_id)
    if existing:
        store.update("validation_object_owner", {"object_id": object_id},
                     {"data_owner": data_owner, "assigned_by": assigned_by, "assigned_at": now})
    else:
        store.insert("validation_object_owner", {"object_id": object_id, "data_owner": data_owner,
                                                 "assigned_by": assigned_by, "assigned_at": now})
    audit.record(store, assigned_by, "validation.assign_data_owner", subject_type="validation_object",
                 subject_id=object_id, details={"data_owner": data_owner})


def data_owner(store, object_id: str) -> str | None:
    row = store.get("validation_object_owner", object_id=object_id)
    return row["data_owner"] if row else None


def accept_deviation(store, run_id: str, cluster_id: str, approver: str, review_by: date, description: str,
                     as_of: date | None = None, now: datetime | None = None,
                     rubrics: RubricSet | None = None) -> str:
    rubrics = rubrics or default_rubrics()
    as_of = as_of or date.today()
    now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
    run = store.get("validation_run", run_id=run_id)
    if run is None:
        raise KeyError(f"validation run {run_id} not found")
    cluster = store.get("mismatch_cluster", cluster_id=cluster_id)
    if cluster is None or cluster["run_id"] != run_id:
        raise KeyError(f"cluster {cluster_id} does not belong to run {run_id}")
    owner = data_owner(store, run["object_id"])
    if owner is None:
        raise ApprovalRequired(f"no data owner registered for {run['object_id']}; assign one first")
    if not approver or approver != owner:
        raise ApprovalRequired(f"only the data owner ({owner}) may accept a deviation on {run['object_id']}")
    if not description:
        raise ValueError("a description of the accepted deviation is required")
    max_days = int(rubrics.get("rubric.validation.deviation.review_by_max_days"))
    if not (as_of < review_by <= as_of + timedelta(days=max_days)):
        raise ValueError(f"review_by must be after {as_of} and at most {max_days} days later")
    deviation_id = stable_id("DEV", run_id, cluster_id)
    if store.get("accepted_deviation", deviation_id=deviation_id):
        return deviation_id
    store.insert("accepted_deviation", {
        "deviation_id": deviation_id, "run_id": run_id, "cluster_id": cluster_id, "description": description,
        "approver": approver, "approved_at": now, "review_by": review_by,
    })
    store.insert("accepted_deviation_scope", {
        "deviation_id": deviation_id, "object_id": run["object_id"], "level": run["level"],
        "signature": cluster["signature"], "known_issue_id": cluster["known_issue_id"],
    })
    store.insert("approval", {
        "approval_id": stable_id("APR", deviation_id, approver), "subject_type": "accepted_deviation",
        "subject_id": deviation_id, "approver": approver, "decision": "approved",
        "comment": f"{description} (review by {review_by.isoformat()})", "decided_at": now,
    })
    audit.record(store, approver, "validation.accept_deviation", subject_type="accepted_deviation",
                 subject_id=deviation_id, details={"run_id": run_id, "cluster_id": cluster_id,
                                                   "signature": cluster["signature"],
                                                   "known_issue_id": cluster["known_issue_id"],
                                                   "review_by": review_by.isoformat()})
    return deviation_id


def deviations(store, as_of: date) -> list[dict]:
    rows = store.query(
        "SELECT d.deviation_id, d.run_id, d.cluster_id, d.description, d.approver, d.approved_at, d.review_by, "
        "s.object_id, s.level, s.signature, s.known_issue_id FROM accepted_deviation d "
        "JOIN accepted_deviation_scope s ON s.deviation_id = d.deviation_id ORDER BY s.object_id, d.deviation_id")
    for r in rows:
        r["expired"] = r["review_by"] < as_of
    return rows
