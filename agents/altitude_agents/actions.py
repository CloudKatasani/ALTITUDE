"""Autonomy enforcement (Section 18.1) and the immutable agent-action log.

Every action is a sequence of rows in ``agent_action`` (append-only; each status transition is a new
row with the next ``seq``)::

    proposed -> approved -> executed [-> rolled_back]      (L2: a recorded human approval is mandatory)
    proposed -> executed [-> rolled_back]                   (L3: pre-approved catalogue only)
    proposed -> rejected | failed

Rules enforced here, independent of what an agent asks for:

- L0/L1 actions are never executable (observe/report and recommend only).
- **L2** actions execute only when an ``approval`` row with ``decision='approved'`` exists for the action,
  from an authorised human (never an agent identity); otherwise :class:`ApprovalRequired` is raised.
- **L3** actions execute only when the tenant's pre-approved action catalogue lists the action type for
  this agent, the target is in scope, every parameter is inside its blast-radius bounds, the per-run and
  per-day execution limits hold and the change window is open; otherwise :class:`ActionRefused` is raised
  and the refusal is logged. A guard metric is captured at execution and re-checked afterwards; a
  regression beyond the rubric tolerance rolls the change back automatically and logs ``rolled_back``.
- Actions whose underlying inference needs human review cannot execute until the review clears.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from altitude.core import audit
from altitude.core.ai import ReviewQueue
from altitude.core.errors import ApprovalRequired
from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import Store, register_append_only

from .catalogue import ActionCatalogue, AgentSpec, PreApproved, TenantPolicy, level_rank, load_agent_catalogue, min_level
from .errors import ActionRefused, AutonomyViolation
from .executor import Executor, forbidden_in, render_sql
from .telemetry import Telemetry
from .tools import TOOLS

register_append_only("agent_run_log", "agent_tool_call", "agent_eval_result")

TERMINAL = {"executed", "rolled_back", "rejected", "failed"}
_DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- guard metrics
def _warehouse_queued_load(tel: Telemetry, target: str, hours: float) -> float:
    rows = TOOLS["warehouse_load"].fn(tel, hours=hours, warehouse=target)
    return float(rows[0]["AVG_QUEUED"]) if rows and rows[0]["AVG_QUEUED"] is not None else 0.0


GUARD_METRICS: dict[str, Callable[[Telemetry, str, float], float]] = {
    "warehouse_queued_load": _warehouse_queued_load,
}


# --------------------------------------------------------------------------- data shapes
@dataclass
class ProposedAction:
    action_type: str
    target: str
    params: dict
    autonomy: str                       # level the agent asks for
    confidence: float
    rationale: str
    evidence: list[str] = field(default_factory=list)
    summary: str = ""
    finding_key: str | None = None      # links the action to the finding/inference that motivated it


@dataclass
class ActionRecord:
    action_id: str
    action_type: str
    target: str | None
    autonomy: str
    status: str
    seq: int
    payload: dict


@dataclass
class GuardResult:
    action_id: str
    metric: str
    baseline: float
    observed: float
    tolerance: float
    regressed: bool


# --------------------------------------------------------------------------- the log
class ActionLog:
    """Append-only access to ``agent_action``: there is no update or delete path."""

    def __init__(self, store: Store, clock: Callable[[], datetime] = _utcnow):
        self.store = store
        self.clock = clock

    def append(self, *, action_id: str, run_id: str, agent_id: str, autonomy: str, action_type: str,
               target: str | None, payload: dict, status: str, actor: str, rollback_payload: dict | None = None,
               confidence: float | None = None, rationale: str | None = None) -> int:
        seq = int(self.store.scalar("SELECT coalesce(max(seq), 0) FROM agent_action WHERE action_id = ?",
                                    [action_id])) + 1
        self.store.insert("agent_action", {
            "action_id": action_id, "seq": seq, "run_id": run_id, "agent_id": agent_id, "autonomy": autonomy,
            "action_type": action_type, "target": target, "payload": payload, "rollback_payload": rollback_payload,
            "confidence": confidence, "rationale": rationale, "status": status, "actor": actor,
            "recorded_at": self.clock()})
        return seq

    def history(self, action_id: str) -> list[dict]:
        return self.store.query("SELECT * FROM agent_action WHERE action_id = ? ORDER BY seq", [action_id])

    def latest(self, action_id: str) -> dict:
        rows = self.store.query("SELECT * FROM agent_action WHERE action_id = ? ORDER BY seq DESC LIMIT 1",
                                [action_id])
        if not rows:
            raise KeyError(f"unknown action {action_id}")
        return rows[0]

    def first(self, action_id: str) -> dict:
        return self.history(action_id)[0]

    @staticmethod
    def payload(row: dict) -> dict:
        import json

        p = row.get("payload")
        return json.loads(p) if isinstance(p, str) else (p or {})


# --------------------------------------------------------------------------- the gateway
class ActionGateway:
    def __init__(self, store: Store, policy: TenantPolicy, catalogue: ActionCatalogue | None = None,
                 agents: dict[str, AgentSpec] | None = None, rubrics: RubricSet | None = None,
                 clock: Callable[[], datetime] = _utcnow, review: ReviewQueue | None = None):
        self.store = store
        self.policy = policy
        self.catalogue = catalogue or ActionCatalogue.load()
        self.agents = agents or load_agent_catalogue()
        self.rubrics = rubrics or default_rubrics()
        self.clock = clock
        self.log = ActionLog(store, clock)
        self.review = review or ReviewQueue(store, self.rubrics)

    # ------------------------------------------------------------------ helpers
    def _record(self, row: dict) -> ActionRecord:
        return ActionRecord(row["action_id"], row["action_type"], row["target"], row["autonomy"], row["status"],
                            row["seq"], ActionLog.payload(row))

    def get(self, action_id: str) -> ActionRecord:
        return self._record(self.log.latest(action_id))

    def _ref(self, ref: str) -> Any:
        return self.rubrics.get(ref)

    # ------------------------------------------------------------------ recommendations (L0/L1)
    def record_recommendation(self, run_id: str, agent: AgentSpec, key: str, summary: str, confidence: float,
                              rationale: str, evidence: list[str], level: str = "L1",
                              inference_id: str | None = None) -> ActionRecord:
        action_id = stable_id("ACT", run_id, "recommendation", key)
        self.log.append(action_id=action_id, run_id=run_id, agent_id=agent.agent_id, autonomy=level,
                        action_type="recommendation", target=key,
                        payload={"summary": summary, "evidence": evidence, "executable": False,
                                 "inference_id": inference_id},
                        status="proposed", actor=agent.service_user, confidence=confidence, rationale=rationale)
        return self.get(action_id)

    def record_platform_action(self, run_id: str, agent: AgentSpec, action_type: str, target: str, payload: dict,
                               rationale: str) -> ActionRecord:
        """Control-plane side effects of reporting (open incident, notify owner): L0, no client-system change."""
        action_id = stable_id("ACT", run_id, action_type, target)
        self.log.append(action_id=action_id, run_id=run_id, agent_id=agent.agent_id, autonomy="L0",
                        action_type=action_type, target=target, payload=payload, status="executed",
                        actor=agent.service_user, confidence=None, rationale=rationale)
        return self.get(action_id)

    # ------------------------------------------------------------------ propose
    def propose(self, run_id: str, agent: AgentSpec, proposal: ProposedAction, inference_id: str | None = None,
                needs_review: bool = False, review_subject: tuple[str, str] | None = None) -> ActionRecord:
        if proposal.action_type not in agent.action_types:
            raise AutonomyViolation(f"{agent.agent_id} may not draft {proposal.action_type!r} "
                                    f"(allowed: {list(agent.action_types)})")
        atype = self.catalogue.types.get(proposal.action_type)
        if atype is None:
            raise ActionRefused(f"unknown action type {proposal.action_type!r}")
        effective = min_level(proposal.autonomy, agent.action_autonomy(proposal.action_type),
                              self.policy.cap(agent.agent_id))
        if needs_review and level_rank(effective) > level_rank("L2"):
            effective = "L2"   # low-confidence output never runs unattended
        sql = None
        if atype.sql_template:
            sql = render_sql(atype.sql_template, proposal.target, proposal.params, atype.params)
            bad = forbidden_in(sql, agent.forbidden_statements)
            if bad:
                raise ActionRefused(f"{agent.agent_id} guardrail: {bad!r} statements are forbidden ({sql})")
        action_id = stable_id("ACT", run_id, proposal.action_type, proposal.target, proposal.params, proposal.autonomy)
        payload = {"params": proposal.params, "sql": sql, "summary": proposal.summary, "evidence": proposal.evidence,
                   "requested_autonomy": proposal.autonomy, "executable": atype.executable,
                   "inference_id": inference_id, "needs_review": needs_review,
                   "review_subject": list(review_subject) if review_subject else None,
                   "tenant_id": self.policy.tenant_id}
        self.log.append(action_id=action_id, run_id=run_id, agent_id=agent.agent_id, autonomy=effective,
                        action_type=proposal.action_type, target=proposal.target, payload=payload, status="proposed",
                        actor=agent.service_user, confidence=proposal.confidence, rationale=proposal.rationale)
        return self.get(action_id)

    # ------------------------------------------------------------------ human decisions
    def _agent_identities(self) -> set[str]:
        out = set()
        for a in self.agents.values():
            out |= {a.service_user.upper(), a.service_role.upper(), a.agent_id.upper()}
        return out

    def approve(self, action_id: str, approver: str, approver_role: str | None = None,
                comment: str | None = None) -> ActionRecord:
        return self._decide(action_id, approver, approver_role, "approved", comment)

    def reject(self, action_id: str, approver: str, approver_role: str | None = None,
               comment: str | None = None) -> ActionRecord:
        return self._decide(action_id, approver, approver_role, "rejected", comment)

    def _decide(self, action_id: str, approver: str, approver_role: str | None, decision: str,
                comment: str | None) -> ActionRecord:
        if not approver:
            raise ApprovalRequired("a named human approver is required")
        if approver.upper() in self._agent_identities():
            raise ApprovalRequired(f"agent identity {approver!r} cannot approve agent actions")
        latest = self.log.latest(action_id)
        if latest["status"] != "proposed":
            raise ActionRefused(f"action {action_id} is {latest['status']}; only proposed actions can be decided")
        if latest["action_type"] == "recommendation":
            raise ActionRefused("recommendations are not executable; implement them through change management")
        allowed = self.policy.approvers.get(latest["action_type"])
        if allowed and approver not in allowed and (approver_role or "") not in allowed:
            raise ApprovalRequired(f"{approver!r} is not an authorised approver for {latest['action_type']} "
                                   f"(owners: {list(allowed)})")
        now = self.clock()
        self.store.insert("approval", {"approval_id": f"APR-{uuid.uuid4().hex[:12].upper()}",
                                       "subject_type": "agent_action", "subject_id": action_id, "approver": approver,
                                       "decision": decision, "comment": comment, "decided_at": now})
        payload = ActionLog.payload(latest)
        payload = {**payload, "approver_role": approver_role}
        self.log.append(action_id=action_id, run_id=latest["run_id"], agent_id=latest["agent_id"],
                        autonomy=latest["autonomy"], action_type=latest["action_type"], target=latest["target"],
                        payload=payload, status=decision, actor=approver,
                        confidence=float(latest["confidence"]) if latest["confidence"] is not None else None,
                        rationale=comment or latest["rationale"])
        audit.record(self.store, approver, f"agent_action.{decision}", subject_type="agent_action",
                     subject_id=action_id, tenant_id=self.policy.tenant_id)
        return self.get(action_id)

    def approvals(self, action_id: str) -> list[dict]:
        return self.store.query("SELECT * FROM approval WHERE subject_type = 'agent_action' AND subject_id = ? "
                                "ORDER BY decided_at", [action_id])

    # ------------------------------------------------------------------ execution
    def execute(self, action_id: str, executor: Executor, telemetry: Telemetry | None = None) -> ActionRecord:
        first = self.log.first(action_id)
        latest = self.log.latest(action_id)
        payload = ActionLog.payload(first)
        level = first["autonomy"]
        agent = self.agents[first["agent_id"]]
        if latest["status"] in TERMINAL:
            raise ActionRefused(f"action {action_id} is already {latest['status']}")
        if not payload.get("executable") or first["action_type"] == "recommendation":
            raise ActionRefused(f"{first['action_type']} is a draft delivered for human implementation; "
                                "agents never execute it")
        if level_rank(level) < level_rank("L2"):
            raise AutonomyViolation(f"{level} actions only observe or recommend; {action_id} cannot execute")
        subject = payload.get("review_subject")
        if payload.get("needs_review") and subject and not self.review.is_cleared(subject[0], subject[1]):
            raise ApprovalRequired(f"{action_id} rests on a low-confidence inference awaiting human review")

        entry: PreApproved | None = None
        if level == "L2":
            decisions = self.approvals(action_id)
            if latest["status"] != "approved" or not decisions or decisions[-1]["decision"] != "approved":
                audit.record(self.store, agent.service_user, "agent_action.execution_refused", actor_type="agent",
                             subject_type="agent_action", subject_id=action_id, tenant_id=self.policy.tenant_id,
                             details={"reason": "no recorded approval"})
                raise ApprovalRequired(f"L2 action {action_id} ({first['action_type']} on {first['target']}) "
                                       "requires a recorded human approval before it can execute")
            actor = decisions[-1]["approver"]
        else:
            entry = self._check_pre_approved(first, payload, agent, telemetry)
            actor = agent.service_user

        atype = self.catalogue.types[first["action_type"]]
        previous = {}
        if atype.capture:
            state = executor.current(atype.object_type, first["target"])
            previous = {k: state.get(k) for k in atype.capture}
        rollback_sql = (render_sql(atype.rollback_template, first["target"], payload["params"], atype.params, previous)
                        if atype.rollback_template else None)
        guard_info = None
        if entry and entry.guard and telemetry is not None:
            hours = float(self._ref(entry.guard["observation_hours_threshold_ref"]))
            baseline = GUARD_METRICS[entry.guard["metric"]](telemetry, first["target"], hours)
            guard_info = {"metric": entry.guard["metric"], "baseline": baseline, "entry": entry.entry_id}
        base = {**payload, "previous": previous, "guard": guard_info, "pre_approved_entry": entry.entry_id if entry else None}
        try:
            executor.run(payload["sql"])
        except Exception as e:  # noqa: BLE001 - every failure is logged, then re-raised
            self.log.append(action_id=action_id, run_id=first["run_id"], agent_id=first["agent_id"], autonomy=level,
                            action_type=first["action_type"], target=first["target"],
                            payload={**base, "error": str(e)}, status="failed", actor=actor,
                            confidence=_f(first["confidence"]), rationale=first["rationale"])
            raise
        self.log.append(action_id=action_id, run_id=first["run_id"], agent_id=first["agent_id"], autonomy=level,
                        action_type=first["action_type"], target=first["target"],
                        payload={**base, "executed_sql": payload["sql"]}, status="executed", actor=actor,
                        rollback_payload={"sql": rollback_sql} if rollback_sql else None,
                        confidence=_f(first["confidence"]), rationale=first["rationale"])
        audit.record(self.store, actor, "agent_action.executed", actor_type="agent" if level == "L3" else "human",
                     subject_type="agent_action", subject_id=action_id, tenant_id=self.policy.tenant_id,
                     details={"sql": payload["sql"], "autonomy": level})
        return self.get(action_id)

    def _refuse(self, first: dict, payload: dict, agent: AgentSpec, reason: str) -> None:
        self.log.append(action_id=first["action_id"], run_id=first["run_id"], agent_id=first["agent_id"],
                        autonomy=first["autonomy"], action_type=first["action_type"], target=first["target"],
                        payload={**payload, "refusal": reason}, status="rejected", actor=agent.service_user,
                        confidence=_f(first["confidence"]), rationale=reason)
        audit.record(self.store, agent.service_user, "agent_action.refused", actor_type="agent",
                     subject_type="agent_action", subject_id=first["action_id"], tenant_id=self.policy.tenant_id,
                     details={"reason": reason})
        raise ActionRefused(reason)

    def _check_pre_approved(self, first: dict, payload: dict, agent: AgentSpec,
                            telemetry: Telemetry | None) -> PreApproved:
        atype, target = first["action_type"], first["target"]
        entries = [e for e in self.catalogue.entries_for(self.policy.tenant_id, atype, agent.agent_id)
                   if e.max_autonomy == "L3"]
        if not entries:
            self._refuse(first, payload, agent, f"{atype} is not in tenant {self.policy.tenant_id!r}'s pre-approved "
                                                f"action catalogue for {agent.agent_id}; L3 execution refused")
        in_scope = [e for e in entries if e.in_scope(target)]
        if not in_scope:
            self._refuse(first, payload, agent, f"{target} is outside the pre-approved scope for {atype}")
        entry = in_scope[0]
        params = payload.get("params") or {}
        for name, bounds in entry.blast_radius.get("param_bounds", {}).items():
            value = params.get(name)
            lo = self._ref(bounds["min_threshold_ref"]) if "min_threshold_ref" in bounds else None
            hi = self._ref(bounds["max_threshold_ref"]) if "max_threshold_ref" in bounds else None
            if value is None or (lo is not None and value < lo) or (hi is not None and value > hi):
                self._refuse(first, payload, agent, f"{name}={value!r} exceeds the blast-radius bounds "
                                                    f"[{lo}, {hi}] of {entry.entry_id}")
        per_run = int(self._ref(entry.blast_radius["max_targets_per_run_threshold_ref"]))
        done_run = self.store.scalar(
            "SELECT count(DISTINCT action_id) FROM agent_action WHERE run_id = ? AND action_type = ? "
            "AND status = 'executed' AND autonomy = 'L3'", [first["run_id"], atype])
        if int(done_run) >= per_run:
            self._refuse(first, payload, agent, f"blast radius: {atype} already executed on {done_run} target(s) in "
                                                f"this run (limit {per_run})")
        per_day = int(self._ref(entry.blast_radius["max_executions_per_day_threshold_ref"]))
        now = self.clock()
        done_day = self.store.scalar(
            "SELECT count(*) FROM agent_action a JOIN agent_run r ON a.run_id = r.run_id "
            "WHERE r.tenant_id = ? AND a.action_type = ? AND a.status = 'executed' AND a.autonomy = 'L3' "
            "AND CAST(a.recorded_at AS DATE) = CAST(? AS DATE)", [self.policy.tenant_id, atype, now])
        if int(done_day) >= per_day:
            self._refuse(first, payload, agent, f"blast radius: daily limit of {per_day} {atype} executions reached")
        win = entry.change_window
        if _DAYS[now.weekday()] not in win["days"] or not (win["start_hour_utc"] <= now.hour < win["end_hour_utc"]):
            self._refuse(first, payload, agent, f"outside the change window {win} for {entry.entry_id}")
        if entry.requires_idempotent_flag or self.catalogue.types[atype].idempotent_required:
            flagged = {t.upper() for t in self.policy.idempotent_tasks}
            if telemetry is not None:
                flagged |= {r["FQ_NAME"].upper() for r in TOOLS["task_idempotency"].fn(telemetry)
                            if str(r["TAG_VALUE"]).lower() == "true"}
            if target.upper() not in flagged:
                self._refuse(first, payload, agent, f"{target} is not flagged idempotent in data; rerun needs approval")
        return entry

    # ------------------------------------------------------------------ guard & rollback
    def check_guard(self, action_id: str, telemetry_after: Telemetry, executor: Executor) -> GuardResult | None:
        latest = self.log.latest(action_id)
        if latest["status"] != "executed":
            return None
        payload = ActionLog.payload(latest)
        guard = payload.get("guard")
        if not guard:
            return None
        entry = next(e for e in self.catalogue.pre_approved if e.entry_id == guard["entry"])
        hours = float(self._ref(entry.guard["observation_hours_threshold_ref"]))
        tolerance = float(self._ref(entry.guard["regression_threshold_ref"]))
        observed = GUARD_METRICS[guard["metric"]](telemetry_after, latest["target"], hours)
        result = GuardResult(action_id, guard["metric"], float(guard["baseline"]), observed, tolerance,
                             observed - float(guard["baseline"]) > tolerance)
        agent = self.agents[latest["agent_id"]]
        if result.regressed:
            self.rollback(action_id, executor, actor=agent.service_user,
                          reason=f"guard metric {guard['metric']} regressed: {result.baseline:.3f} -> "
                                 f"{observed:.3f} (tolerance {tolerance})",
                          details={"baseline": result.baseline, "observed": observed, "tolerance": tolerance,
                                   "automatic": True})
        else:
            audit.record(self.store, agent.service_user, "agent_action.guard_ok", actor_type="agent",
                         subject_type="agent_action", subject_id=action_id, tenant_id=self.policy.tenant_id,
                         details={"baseline": result.baseline, "observed": observed, "tolerance": tolerance})
        return result

    def check_all_guards(self, telemetry_after: Telemetry, executor: Executor) -> list[GuardResult]:
        """Re-check every executed, guarded L3 action of this tenant (run after the observation window)."""
        rows = self.store.query(
            "SELECT DISTINCT a.action_id FROM agent_action a JOIN agent_run r ON a.run_id = r.run_id "
            "WHERE r.tenant_id = ? AND a.autonomy = 'L3' AND a.status = 'executed' ORDER BY 1", [self.policy.tenant_id])
        results = []
        for r in rows:
            res = self.check_guard(r["action_id"], telemetry_after, executor)
            if res is not None:
                results.append(res)
        return results

    def rollback(self, action_id: str, executor: Executor, actor: str, reason: str,
                 details: dict | None = None) -> ActionRecord:
        latest = self.log.latest(action_id)
        if latest["status"] != "executed":
            raise ActionRefused(f"only executed actions can be rolled back ({action_id} is {latest['status']})")
        import json

        rb = latest["rollback_payload"]
        rb = json.loads(rb) if isinstance(rb, str) else rb
        if not rb or not rb.get("sql"):
            raise ActionRefused(f"{latest['action_type']} has no rollback template")
        executor.run(rb["sql"])
        payload = {**ActionLog.payload(latest), "rollback_reason": reason, "rollback_sql": rb["sql"],
                   **(details or {})}
        self.log.append(action_id=action_id, run_id=latest["run_id"], agent_id=latest["agent_id"],
                        autonomy=latest["autonomy"], action_type=latest["action_type"], target=latest["target"],
                        payload=payload, status="rolled_back", actor=actor, rollback_payload=rb,
                        confidence=_f(latest["confidence"]), rationale=reason)
        audit.record(self.store, actor, "agent_action.rolled_back", actor_type="agent" if actor.startswith("SVC_") else "human",
                     subject_type="agent_action", subject_id=action_id, tenant_id=self.policy.tenant_id,
                     details={"reason": reason, "sql": rb["sql"]})
        return self.get(action_id)


def _f(v: Any) -> float | None:
    return float(v) if v is not None else None
