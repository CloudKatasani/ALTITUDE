"""Factory state machine (Section 9.2) defined in ``knowledge/planning/factory.yaml``.

Each object in a wave is a work item. Every transition is validated against
the definition (allowed edge, actor type, disposition guard, gate guard,
agent-confidence guard) and recorded append-only in ``factory_transition``
with actor, timestamp, evidence reference and confidence; ``wave_object.state``
holds the current state for boards.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from altitude.core import audit
from altitude.core.errors import AltitudeError, ApprovalRequired
from altitude.core.ids import stable_id
from altitude.core.paths import knowledge_dir
from altitude.core.rubric import RubricSet, default_rubrics

from .gates import gate_passed

ACTOR_TYPES = ("human", "agent", "system")


class InvalidTransition(AltitudeError):
    """The requested state change is not defined by the factory state machine."""


def load_definition(root: Path | None = None) -> dict[str, Any]:
    doc = yaml.safe_load(((root or knowledge_dir()) / "planning" / "factory.yaml").read_text())
    states = {s["state"] for s in doc["states"]}
    for t in doc["transitions"]:
        if t["from"] not in states or t["to"] not in states:
            raise AltitudeError(f"factory transition {t['from']} -> {t['to']} uses an undefined state")
    if doc["initial"] not in states:
        raise AltitudeError(f"factory initial state {doc['initial']!r} is undefined")
    return doc


class Factory:
    def __init__(self, store: Any, rubrics: RubricSet | None = None, definition: dict[str, Any] | None = None):
        self.store = store
        self.rubrics = rubrics or default_rubrics()
        self.definition = definition or load_definition()
        self.initial = self.definition["initial"]
        self.agent_min = float(self.rubrics.get(self.definition["agent_confidence_threshold_ref"]))

    # ------------------------------------------------------------------ queries
    def state(self, wave_id: str, object_id: str) -> str | None:
        row = self.store.get("wave_object", wave_id=wave_id, object_id=object_id)
        return row["state"] if row else None

    def allowed(self, from_state: str) -> list[str]:
        return [t["to"] for t in self.definition["transitions"] if t["from"] == from_state]

    def history(self, object_id: str, wave_id: str | None = None) -> list[dict[str, Any]]:
        if wave_id:
            return self.store.query("SELECT * FROM factory_transition WHERE object_id = ? AND wave_id = ? ORDER BY seq",
                                    [object_id, wave_id])
        return self.store.query("SELECT * FROM factory_transition WHERE object_id = ? ORDER BY wave_id, seq",
                                [object_id])

    def board(self, wave_id: str) -> dict[str, int]:
        rows = self.store.query("SELECT state, count(*) AS n FROM wave_object WHERE wave_id = ? GROUP BY state",
                                [wave_id])
        return {r["state"]: int(r["n"]) for r in rows}

    # ------------------------------------------------------------------ commands
    def enrol(self, wave_id: str, object_id: str, *, evidence_ref: str, confidence: float,
              actor: str = "altitude.assessment", at: datetime | None = None) -> None:
        """Add an object to a wave as ``discovered`` and record its classification transition."""
        if self.store.get("wave_object", wave_id=wave_id, object_id=object_id):
            return
        self.store.insert("wave_object", {"wave_id": wave_id, "object_id": object_id, "state": self.initial})
        self.transition(wave_id, object_id, "classified", actor=actor, actor_type="system", evidence_ref=evidence_ref,
                        confidence=confidence, note="classified by the assessment engine", at=at)

    def transition(self, wave_id: str, object_id: str, to_state: str, *, actor: str, actor_type: str,
                   evidence_ref: str, confidence: float, note: str | None = None,
                   at: datetime | None = None) -> dict[str, Any]:
        current = self.state(wave_id, object_id)
        if current is None:
            raise InvalidTransition(f"object {object_id} is not enrolled in wave {wave_id}")
        rule = next((t for t in self.definition["transitions"] if t["from"] == current and t["to"] == to_state), None)
        if rule is None:
            raise InvalidTransition(f"{current} -> {to_state} is not a factory transition "
                                    f"(allowed: {', '.join(self.allowed(current)) or 'none'})")
        if not actor or not evidence_ref:
            raise ApprovalRequired("every transition needs an actor and an evidence reference")
        if actor_type not in ACTOR_TYPES:
            raise ValueError(f"invalid actor_type {actor_type!r}")
        confidence = float(confidence)
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("confidence must be within [0, 1]")
        if rule.get("actor_types") and actor_type not in rule["actor_types"]:
            raise ApprovalRequired(f"{current} -> {to_state} must be made by: {', '.join(rule['actor_types'])}")
        if actor_type == "agent" and confidence < self.agent_min:
            raise ApprovalRequired(f"agent confidence {confidence:.2f} is below {self.agent_min:.2f}; "
                                   "a human must make this transition")
        wave = self.store.get("wave", wave_id=wave_id)
        if rule.get("requires_gate"):
            if not gate_passed(self.store, rule["requires_gate"], engagement_id=(wave or {}).get("engagement_id")):
                raise ApprovalRequired(f"{current} -> {to_state} requires a passing '{rule['requires_gate']}' gate")
        if rule.get("when_disposition"):
            rows = self.store.query("SELECT disposition FROM object_disposition WHERE object_id = ? "
                                    "ORDER BY snapshot_id DESC", [object_id])
            if not rows or rows[0]["disposition"] != rule["when_disposition"]:
                raise InvalidTransition(f"{current} -> {to_state} only applies to '{rule['when_disposition']}' objects")
        seq = int(self.store.scalar("SELECT count(*) FROM factory_transition WHERE wave_id = ? AND object_id = ?",
                                    [wave_id, object_id])) + 1
        record = {
            "transition_id": stable_id("FT", wave_id, object_id, seq, length=10), "wave_id": wave_id,
            "object_id": object_id, "seq": seq, "from_state": current, "to_state": to_state, "actor": actor,
            "actor_type": actor_type, "evidence_ref": evidence_ref, "confidence": confidence, "note": note,
            "recorded_at": at or datetime.now(timezone.utc).replace(tzinfo=None),
        }
        self.store.insert("factory_transition", record)
        self.store.update("wave_object", {"wave_id": wave_id, "object_id": object_id}, {"state": to_state})
        audit.record(self.store, actor, "factory.transition", actor_type=actor_type, subject_type="wave_object",
                     subject_id=f"{wave_id}/{object_id}",
                     details={"from": current, "to": to_state, "evidence_ref": evidence_ref, "confidence": confidence})
        return record
