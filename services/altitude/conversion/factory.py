"""Factory state machine (Section 9.2).

Each object is a work item moving through ``Discovered -> Classified -> Converted -> AI-remediated ->
Reviewed -> Unit-tested -> ...``. Every transition is an append-only ``conversion_lane_transition`` row with the
actor (human or agent identity), timestamp, evidence reference and confidence. Allowed transitions are
data (``knowledge/conversion/workflow.yaml``); anything else raises :class:`InvalidTransition`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from altitude.core import audit
from altitude.core.errors import AltitudeError
from altitude.core.ids import stable_id

from . import kb


class InvalidTransition(AltitudeError):
    """A factory state transition not allowed by the workflow definition."""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def current_state(store: Any, object_id: str, lane: str = "code") -> str | None:
    rows = store.query(
        "SELECT to_state FROM conversion_lane_transition WHERE object_id=? AND lane=? ORDER BY seq DESC LIMIT 1",
        [object_id, lane],
    )
    return rows[0]["to_state"] if rows else None


def history(store: Any, object_id: str, lane: str = "code") -> list[dict]:
    return store.query(
        "SELECT * FROM conversion_lane_transition WHERE object_id=? AND lane=? ORDER BY seq",
        [object_id, lane],
    )


def transition(store: Any, *, engagement_id: str, object_id: str, to_state: str, actor: str, actor_type: str,
               evidence_ref: str, confidence: float, artifact_id: str | None = None, lane: str = "code") -> dict:
    """Record a factory transition after validating it against the workflow definition."""
    wf = kb.workflow()["factory"]
    if to_state not in wf["states"]:
        raise InvalidTransition(f"unknown factory state {to_state!r}")
    if not actor:
        raise InvalidTransition("a transition requires an actor")
    if actor_type not in {"human", "agent", "system"}:
        raise InvalidTransition(f"invalid actor_type {actor_type!r}")
    if not evidence_ref:
        raise InvalidTransition("a transition requires an evidence reference")
    if not (0.0 <= float(confidence) <= 1.0):
        raise InvalidTransition("confidence must be within [0, 1]")
    current = current_state(store, object_id, lane)
    allowed = wf["transitions"].get(current, []) if current else wf["entry_states"]
    if to_state not in allowed:
        raise InvalidTransition(f"{object_id}: {current or '(none)'} -> {to_state} is not an allowed transition")
    now = _now()
    seq = int(store.scalar("SELECT count(*) FROM conversion_lane_transition WHERE object_id=? AND lane=?",
                           [object_id, lane]) or 0)
    row = {
        "transition_id": stable_id("FTR", object_id, lane, seq, to_state, length=10),
        "seq": seq,
        "engagement_id": engagement_id,
        "object_id": object_id,
        "artifact_id": artifact_id,
        "lane": lane,
        "from_state": current,
        "to_state": to_state,
        "actor": actor,
        "actor_type": actor_type,
        "evidence_ref": evidence_ref,
        "confidence": round(float(confidence), 3),
        "occurred_at": now,
    }
    store.insert("conversion_lane_transition", row)
    status = wf["artifact_status"].get(to_state)
    if artifact_id and status:
        store.update("converted_artifact", {"artifact_id": artifact_id}, {"status": status})
    # keep the planning view (wave_object.state) in step when the object is in a wave
    if store.query("SELECT 1 FROM wave_object WHERE object_id=?", [object_id]):
        store.execute("UPDATE wave_object SET state=? WHERE object_id=?", [to_state, object_id])
    audit.record(store, actor, f"factory.{to_state}", actor_type=actor_type, subject_type="object",
                 subject_id=object_id, details={"from": current, "evidence_ref": evidence_ref,
                                                "confidence": row["confidence"], "artifact_id": artifact_id})
    return row
