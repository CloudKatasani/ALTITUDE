"""Audit events: every human and agent action is recorded (append-only)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


def record(store: Any, actor: str, action: str, *, actor_type: str = "human", subject_type: str | None = None,
           subject_id: str | None = None, details: dict | None = None, tenant_id: str | None = None) -> str:
    if actor_type not in {"human", "agent", "system"}:
        raise ValueError(f"invalid actor_type {actor_type!r}")
    event_id = f"AUD-{uuid.uuid4().hex[:12].upper()}"
    store.insert("audit_event", {
        "event_id": event_id,
        "tenant_id": tenant_id,
        "actor": actor,
        "actor_type": actor_type,
        "action": action,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "details": details or {},
        "occurred_at": datetime.now(timezone.utc).replace(tzinfo=None),
    })
    return event_id


def trail(store: Any, subject_type: str, subject_id: str) -> list[dict]:
    return store.query(
        "SELECT * FROM audit_event WHERE subject_type=? AND subject_id=? ORDER BY occurred_at",
        [subject_type, subject_id],
    )
