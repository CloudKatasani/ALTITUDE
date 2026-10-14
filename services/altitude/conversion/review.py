"""Review workflow, convert_exit gate and promotion (principles 3 & 4, Section 30.2, Appendix C).

An artifact is promotable only when:
- every ``ai_change`` has a named reviewer and a decision (and no review-queue item is still open);
- every change below ``rubric.ai.review_confidence_min`` was approved or modified by a named reviewer;
- the artifact itself has an approved ``review``;
- there are zero open P1 issues (``rubric.conversion.gates``);
- the generated unit tests ran on the final content and met ``rubric.conversion.gates.unit_test_min``.

Promotion records ``promoted_by`` / ``promoted_at`` and the promoted content; it never deploys anything.
"""

from __future__ import annotations

import json
import operator
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from altitude.core import audit
from altitude.core.ai import ReviewQueue
from altitude.core.errors import ApprovalRequired
from altitude.core.generated import stamp
from altitude.core.ids import content_hash
from altitude.core.rubric import RubricSet, default_rubrics

from . import factory, kb
from .remediation import ChangeRecord, assert_not_production, build_manifest, run_pack_tests, splice, write_manifest

DECISIONS = {"approved", "rejected", "modified"}
_OPS = {"==": operator.eq, "!=": operator.ne, ">=": operator.ge, "<=": operator.le, ">": operator.gt,
        "<": operator.lt}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class GateResult:
    gate: str
    artifact_id: str
    passed: bool
    metrics: dict[str, Any]
    failures: list[str] = field(default_factory=list)
    rubric_version: str = ""


class ReviewWorkflow:
    def __init__(self, store: Any, rubrics: RubricSet | None = None):
        self.store = store
        self.rubrics = rubrics or default_rubrics()
        self.queue = ReviewQueue(store, self.rubrics)

    # ------------------------------------------------------------------ helpers
    def _artifact(self, artifact_id: str) -> dict:
        art = self.store.get("converted_artifact", artifact_id=artifact_id)
        if art is None:
            raise KeyError(artifact_id)
        return art

    def _engagement(self, art: dict) -> str:
        return self.store.scalar("SELECT engagement_id FROM conversion_run WHERE run_id=?", [art["run_id"]])

    def _changes(self, artifact_id: str) -> list[dict]:
        return self.store.query(
            "SELECT c.*, p.line_start, p.line_end, p.before_text, p.after_text, p.final_text, p.below_floor, "
            "p.rule_ids FROM ai_change c JOIN ai_change_patch p USING (change_id) WHERE c.artifact_id=? "
            "ORDER BY p.line_start", [artifact_id])

    def _pack(self, artifact_id: str) -> dict | None:
        return self.store.get("pr_pack", artifact_id=artifact_id)

    def _refresh_manifest(self, art: dict) -> None:
        pack = self._pack(art["artifact_id"])
        if not pack:
            return
        changes = [ChangeRecord(
            change_id=r["change_id"], line_start=r["line_start"], line_end=r["line_end"],
            before_text=r["before_text"], after_text=r["after_text"], rule_ids=list(r["rule_ids"] or []),
            issue_ids=list(r["linked_issue_ids"] or []), issue_codes=[], confidence=float(r["confidence"]),
            rationale=r["rationale"], model_id=r["model_id"], prompt_template=r["prompt_template"],
            below_floor=bool(r["below_floor"]), diff=r["diff"],
            tests=[t.split("::")[-1] for t in (r["tests_generated"] or [])]) for r in self._changes(art["artifact_id"])]
        linked = {i for c in changes for i in c.issue_ids}
        unresolved = [i for i in self.store.query(
            "SELECT * FROM conversion_issue WHERE artifact_id=? AND status='open' ORDER BY line, issue_id",
            [art["artifact_id"]]) if i["issue_id"] not in linked]
        write_manifest(Path(pack["path"]), build_manifest(self.store, art, pack["pack_id"], changes, unresolved))

    # ------------------------------------------------------------------ decisions
    def decide_change(self, change_id: str, reviewer: str, decision: str, comment: str | None = None,
                      modified_text: str | None = None) -> None:
        """Record a named reviewer's decision on one AI change."""
        if not reviewer or not reviewer.strip():
            raise ApprovalRequired("a named reviewer is required for every AI change")
        if decision not in DECISIONS:
            raise ValueError(f"invalid decision {decision!r}; expected one of {sorted(DECISIONS)}")
        if decision == "modified" and modified_text is None:
            raise ValueError("decision 'modified' requires the reviewer's modified text")
        change = self.store.get("ai_change", change_id=change_id)
        if change is None:
            raise KeyError(change_id)
        now = _now()
        self.store.update("ai_change", {"change_id": change_id},
                          {"reviewer": reviewer, "decision": decision, "decided_at": now})
        if decision == "modified":
            self.store.update("ai_change_patch", {"change_id": change_id}, {"final_text": modified_text})
        items = self.store.query(
            "SELECT item_id FROM review_item WHERE subject_type='ai_change' AND subject_id=? AND status='open'",
            [change_id])
        if items:
            for it in items:
                self.queue.decide(it["item_id"], reviewer, decision, comment)
        else:
            self.store.insert("review", {"review_id": f"RVW-{uuid.uuid4().hex[:10].upper()}",
                                         "subject_type": "ai_change", "subject_id": change_id,
                                         "reviewer": reviewer, "decision": decision, "comment": comment,
                                         "reviewed_at": now})
        new_status = "fixed" if decision in {"approved", "modified"} else "open"
        for issue_id in change["linked_issue_ids"] or []:
            self.store.update("conversion_issue", {"issue_id": issue_id}, {"status": new_status})
        audit.record(self.store, reviewer, f"ai_change.{decision}", subject_type="ai_change", subject_id=change_id,
                     details={"comment": comment, "artifact_id": change["artifact_id"]})
        self._refresh_manifest(self._artifact(change["artifact_id"]))

    def accept_issue(self, issue_id: str, reviewer: str, justification: str) -> None:
        """Record a named, justified acceptance of an issue left unfixed (e.g. redesigned in a later wave)."""
        if not reviewer or not reviewer.strip():
            raise ApprovalRequired("accepting a conversion issue requires a named reviewer")
        if not justification or not justification.strip():
            raise ApprovalRequired("accepting a conversion issue requires a justification")
        issue = self.store.get("conversion_issue", issue_id=issue_id)
        if issue is None:
            raise KeyError(issue_id)
        self.store.update("conversion_issue", {"issue_id": issue_id}, {"status": "accepted"})
        self.store.insert("review", {"review_id": f"RVW-{uuid.uuid4().hex[:10].upper()}",
                                     "subject_type": "conversion_issue", "subject_id": issue_id,
                                     "reviewer": reviewer, "decision": "approved", "comment": justification,
                                     "reviewed_at": _now()})
        audit.record(self.store, reviewer, "conversion_issue.accepted", subject_type="conversion_issue",
                     subject_id=issue_id, details={"justification": justification})

    def review_artifact(self, artifact_id: str, reviewer: str, decision: str, comment: str | None = None) -> None:
        """Peer review of the whole artifact; requires every AI change to be decided first."""
        if not reviewer or not reviewer.strip():
            raise ApprovalRequired("artifact review requires a named reviewer")
        if decision not in DECISIONS:
            raise ValueError(f"invalid decision {decision!r}")
        art = self._artifact(artifact_id)
        pending = [c["change_id"] for c in self._changes(artifact_id) if not c["reviewer"] or not c["decision"]]
        if pending:
            raise ApprovalRequired(f"AI changes awaiting a reviewer decision: {', '.join(pending)}")
        review_id = f"RVW-{uuid.uuid4().hex[:10].upper()}"
        self.store.insert("review", {"review_id": review_id, "subject_type": "converted_artifact",
                                     "subject_id": artifact_id, "reviewer": reviewer, "decision": decision,
                                     "comment": comment, "reviewed_at": _now()})
        audit.record(self.store, reviewer, f"converted_artifact.review.{decision}",
                     subject_type="converted_artifact", subject_id=artifact_id, details={"comment": comment})
        if decision == "rejected":
            self.store.update("converted_artifact", {"artifact_id": artifact_id}, {"status": "rejected"})
            return
        state = factory.current_state(self.store, art["object_id"])
        if state != "Reviewed":
            factory.transition(self.store, engagement_id=self._engagement(art), object_id=art["object_id"],
                               to_state="Reviewed", actor=reviewer, actor_type="human",
                               evidence_ref=f"review:{review_id}", confidence=1.0, artifact_id=artifact_id)

    # ------------------------------------------------------------------ content & tests
    def final_content(self, artifact_id: str) -> str:
        """Converted content with approved/modified changes applied (rejected/pending changes left out)."""
        converted = self.store.get("artifact_content", artifact_id=artifact_id, kind="converted")["content"]
        patches = []
        for c in self._changes(artifact_id):
            if c["decision"] == "approved":
                patches.append((c["line_start"], c["line_end"], c["after_text"]))
            elif c["decision"] == "modified":
                patches.append((c["line_start"], c["line_end"], c["final_text"]))
        return splice(converted, patches)

    def run_unit_tests(self, artifact_id: str, actor: str = "altitude.conversion.test-runner") -> dict:
        """Write the final content into the PR pack and run the generated tests of accepted changes."""
        art = self._artifact(artifact_id)
        pack = self._pack(artifact_id)
        if pack is None:
            raise ApprovalRequired(f"{artifact_id} has no PR pack; run remediation first")
        pack_dir = Path(pack["path"])
        assert_not_production(pack_dir)
        final = pack_dir / "final" / art["target_path"]
        final.parent.mkdir(parents=True, exist_ok=True)
        content = self.final_content(artifact_id)
        final.write_text(stamp(content, ".sql", f"pr_pack:{pack['pack_id']}/final"))
        self._refresh_manifest(art)
        accepted = {c["change_id"] for c in self._changes(artifact_id) if c["decision"] in {"approved", "modified"}}
        report = run_pack_tests(pack_dir, accepted)
        now = _now()
        self.store.update("pr_pack", {"pack_id": pack["pack_id"]},
                          {"tests_total": report.total, "tests_passed": report.passed, "tested_at": now})
        (pack_dir / "test_results.json").write_text(stamp(json.dumps(
            {"total": report.total, "passed": report.passed, "failures": report.failures,
             "final_content_hash": content_hash(content)}, indent=2), ".json", f"pr_pack:{pack['pack_id']}"))
        if factory.current_state(self.store, art["object_id"]) == "Reviewed":
            factory.transition(self.store, engagement_id=self._engagement(art), object_id=art["object_id"],
                               to_state="Unit-tested", actor=actor, actor_type="system",
                               evidence_ref=f"pr_pack:{pack['pack_id']}/test_results.json",
                               confidence=report.pass_rate, artifact_id=artifact_id)
        return {"total": report.total, "passed": report.passed, "failures": report.failures,
                "pass_rate": report.pass_rate}

    # ------------------------------------------------------------------ gate & promotion
    def metrics(self, artifact_id: str) -> dict[str, Any]:
        self._artifact(artifact_id)
        blocking = list(self.rubrics.get("rubric.conversion.blocking_severities"))
        issues = self.store.query("SELECT severity, status FROM conversion_issue WHERE artifact_id=?", [artifact_id])
        changes = self._changes(artifact_id)
        open_items = {r["subject_id"] for r in self.store.query(
            "SELECT subject_id FROM review_item WHERE subject_type='ai_change' AND status='open'")}
        unreviewed = [c for c in changes if not c["reviewer"] or not c["decision"] or c["change_id"] in open_items]
        low_unreviewed = [c for c in changes if c["below_floor"] and (
            not c["reviewer"] or c["decision"] not in DECISIONS or c["change_id"] in open_items)]
        reviews = self.store.query(
            "SELECT decision FROM review WHERE subject_type='converted_artifact' AND subject_id=? "
            "ORDER BY reviewed_at DESC LIMIT 1", [artifact_id])
        pack = self._pack(artifact_id)
        if pack is None or pack["tested_at"] is None:
            pass_rate = None
        else:
            pass_rate = (pack["tests_passed"] / pack["tests_total"]) if pack["tests_total"] else 1.0
        return {
            "open_p1_ewis": sum(1 for i in issues if i["status"] == "open" and i["severity"] in blocking),
            "ai_changes_unreviewed": len(unreviewed),
            "low_confidence_changes_unreviewed": len(low_unreviewed),
            "artifact_review_approved": bool(reviews) and reviews[0]["decision"] in {"approved", "modified"},
            "unit_test_pass_rate": pass_rate,
        }

    def gate(self, artifact_id: str, gate: str = "convert_exit") -> GateResult:
        rules = kb.workflow()["gates"][gate]
        m = self.metrics(artifact_id)
        failures = []
        for rule in rules:
            actual = m.get(rule["metric"])
            expected = self.rubrics.get(rule["threshold_ref"]) if "threshold_ref" in rule else rule["value"]
            if actual is None or not _OPS[rule["op"]](actual, expected):
                failures.append(f"{rule['metric']}={actual!r} (required {rule['op']} {expected!r})")
        return GateResult(gate, artifact_id, not failures, m, failures, self.rubrics.version)

    def promote(self, artifact_id: str, promoted_by: str) -> dict:
        """Mark an artifact promotable/promoted after the convert_exit gate passes. Records the approver."""
        if not promoted_by or not promoted_by.strip():
            raise ApprovalRequired("promotion requires a named approver (promoted_by)")
        art = self._artifact(artifact_id)
        if art["status"] == "promoted":
            return art
        result = self.gate(artifact_id)
        if not result.passed:
            raise ApprovalRequired(f"{artifact_id} is not promotable: " + "; ".join(result.failures))
        content = self.final_content(artifact_id)
        now = _now()
        self.store.insert("artifact_content", {"artifact_id": artifact_id, "kind": "promoted",
                                               "content_hash": content_hash(content), "content": content,
                                               "created_at": now})
        self.store.update("converted_artifact", {"artifact_id": artifact_id},
                          {"status": "promoted", "promoted_by": promoted_by, "promoted_at": now})
        audit.record(self.store, promoted_by, "converted_artifact.promoted", subject_type="converted_artifact",
                     subject_id=artifact_id, details={"gate": result.gate, "metrics": result.metrics,
                                                      "rubric_version": result.rubric_version,
                                                      "content_hash": content_hash(content)})
        return self._artifact(artifact_id)
