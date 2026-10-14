"""Agent runtime (Section 18.3): scoped tools in, logged findings and gated actions out.

``AgentRunner.run`` executes one agent against read-only telemetry and records:

- ``agent_run``        the run (status running -> completed/failed);
- ``agent_tool_call``  every tool call (append-only);
- ``ai_inference``     every finding as an :class:`~altitude.core.ai.Inference` (confidence + rationale);
                       low-confidence findings land in the review queue;
- ``agent_action``     every recommendation, platform action and drafted change (append-only, via the
                       :class:`~altitude_agents.actions.ActionGateway`, which enforces autonomy levels);
- ``agent_run_log``    inputs, output and decision summary (append-only).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable

from altitude.core.ai import Inference, ReviewQueue, TemplateProvider
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import Store, json_safe

from .actions import ActionGateway, ActionRecord, ProposedAction, _utcnow
from .catalogue import ActionCatalogue, AgentSpec, TenantPolicy, level_rank, load_agent_catalogue, load_tenant_policy
from .errors import ActionRefused, AgentNotPromoted
from .executor import Executor
from .telemetry import Telemetry
from .tools import ToolContext


@dataclass
class Finding:
    kind: str                 # anomaly | forecast | rightsizing | root_cause | access_issue | dq_cluster | impact | ...
    subject: str              # object the finding is about (warehouse, task, user, table, bundle entry)
    title: str
    confidence: float
    rationale: str
    detail: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    recommendation: str | None = None   # L1 recommendation text, if any

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.subject}"


@dataclass
class Incident:
    key: str
    severity: str
    title: str
    owner: str | None
    tables: list[str]
    probable_cause: str
    confidence: float
    rationale: str


@dataclass
class AgentResult:
    findings: list[Finding] = field(default_factory=list)
    actions: list[ProposedAction] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    summary: str = ""


@dataclass
class AgentContext:
    spec: AgentSpec
    tools: ToolContext
    policy: TenantPolicy
    rubrics: RubricSet
    as_of: datetime

    def r(self, path: str) -> Any:
        """Rubric value ``rubric.agents.<path>``."""
        return self.rubrics.get(f"rubric.agents.{path}")

    def call(self, tool: str, **kwargs: Any) -> list[dict]:
        return self.tools.call(tool, **kwargs)


class BaseAgent:
    agent_id: str = ""
    version: str = "1.0.0"

    def run(self, ctx: AgentContext) -> AgentResult:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass
class RunReport:
    run_id: str
    agent_id: str
    version: str
    tenant_id: str
    telemetry_ref: str
    findings: list[dict]
    actions: list[ActionRecord]
    refused: list[dict]
    incidents: list[dict]
    tool_calls: int
    summary: str

    def action(self, action_type: str, target: str) -> ActionRecord | None:
        return next((a for a in self.actions if a.action_type == action_type and a.target == target), None)

    def to_dict(self) -> dict:
        d = asdict(self)
        return json_safe(d)


def registry() -> dict[str, type[BaseAgent]]:
    from .agents import AGENTS

    return dict(AGENTS)


class AgentRunner:
    def __init__(self, store: Store, tenant_id: str = "default", rubrics: RubricSet | None = None,
                 agents: dict[str, AgentSpec] | None = None, action_catalogue: ActionCatalogue | None = None,
                 policy: TenantPolicy | None = None, clock: Callable[[], datetime] = _utcnow):
        self.store = store
        self.tenant_id = tenant_id
        self.rubrics = rubrics or default_rubrics()
        self.agents = agents or load_agent_catalogue()
        self.policy = policy or load_tenant_policy(tenant_id)
        self.clock = clock
        self.review = ReviewQueue(store, self.rubrics)
        self.provider = TemplateProvider()
        self.gateway = ActionGateway(store, self.policy, action_catalogue or ActionCatalogue.load(), self.agents,
                                     self.rubrics, clock, self.review)

    # ------------------------------------------------------------------ registration & promotion state
    def ensure_agent(self, spec: AgentSpec) -> None:
        if not self.store.get("agent", agent_id=spec.agent_id):
            self.store.insert("agent", {"agent_id": spec.agent_id, "name": spec.name, "max_autonomy": spec.max_autonomy,
                                        "service_identity": spec.service_user, "tool_scope": list(spec.tool_scope)})

    def promoted_version(self, agent_id: str) -> str | None:
        rows = self.store.query("SELECT version FROM agent_version WHERE agent_id = ? AND eval_passed "
                                "ORDER BY released_at DESC, version DESC LIMIT 1", [agent_id])
        return rows[0]["version"] if rows else None

    # ------------------------------------------------------------------ run
    def run(self, agent_id: str, telemetry: Telemetry, trigger: str = "manual", executor: Executor | None = None,
            agent: BaseAgent | None = None, require_promoted: bool = True, auto_execute: bool = True,
            fallback_to_l2: bool = True) -> RunReport:
        spec = self.agents[agent_id]
        impl = agent or registry()[agent_id]()
        if require_promoted:
            promoted = self.promoted_version(agent_id)
            if promoted != impl.version:
                raise AgentNotPromoted(f"{agent_id} version {impl.version} has not passed its evaluation suite "
                                       f"(promoted version: {promoted})")
        self.ensure_agent(spec)
        run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
        self.store.insert("agent_run", {"run_id": run_id, "agent_id": agent_id, "agent_version": impl.version,
                                        "tenant_id": self.tenant_id, "trigger": trigger, "inputs_ref": telemetry.ref,
                                        "started_at": self.clock(), "status": "running"})
        tools = ToolContext(agent_id, spec.tool_scope, telemetry, self.rubrics)
        ctx = AgentContext(spec, tools, self.policy, self.rubrics, telemetry.as_of)
        try:
            result = impl.run(ctx)
        except Exception:
            self._log_tool_calls(run_id, tools)
            self.store.update("agent_run", {"run_id": run_id}, {"status": "failed", "completed_at": self.clock()})
            raise

        findings_out: list[dict] = []
        inference_by_key: dict[str, Inference] = {}
        for f in result.findings:
            inf = Inference(kind=f"agent.{f.kind}", subject_type="agent_finding", subject_id=f"{agent_id}:{f.key}",
                            output=self.provider.complete(spec.prompt_template or "", f.title), confidence=f.confidence,
                            rationale=f.rationale, model_id=self.provider.model_id,
                            prompt_template=spec.prompt_template or f"agents/{agent_id.lower()}@0",
                            provider=self.provider.name, inputs_ref=telemetry.ref, tenant_id=self.tenant_id)
            self.review.record(inf, sample=False)
            inference_by_key[f.key] = inf
            item = {"kind": f.kind, "subject": f.subject, "title": f.title, "confidence": f.confidence,
                    "rationale": f.rationale, "detail": json_safe(f.detail), "evidence": f.evidence,
                    "recommendation": f.recommendation, "inference_id": inf.inference_id,
                    "needs_review": inf.needs_review}
            findings_out.append(item)
            if f.recommendation:
                self.gateway.record_recommendation(run_id, spec, f.key, f.recommendation, f.confidence, f.rationale,
                                                   f.evidence, level=min(spec.max_autonomy, "L1", key=level_rank),
                                                   inference_id=inf.inference_id)

        actions: list[ActionRecord] = []
        refused: list[dict] = []
        for p in result.actions:
            inf = inference_by_key.get(p.finding_key or "")
            if inf is None:
                inf = Inference(kind="agent.action_draft", subject_type="agent_finding",
                                subject_id=f"{agent_id}:{p.action_type}:{p.target}", output=p.summary or p.action_type,
                                confidence=p.confidence, rationale=p.rationale, model_id=self.provider.model_id,
                                prompt_template=spec.prompt_template or "", provider=self.provider.name,
                                inputs_ref=telemetry.ref, tenant_id=self.tenant_id)
                self.review.record(inf, sample=False)
            rec = self.gateway.propose(run_id, spec, p, inference_id=inf.inference_id, needs_review=inf.needs_review,
                                       review_subject=(inf.subject_type, inf.subject_id))
            if rec.autonomy == "L3" and executor is not None and auto_execute:
                try:
                    rec = self.gateway.execute(rec.action_id, executor, telemetry)
                except ActionRefused as e:
                    refused.append({"action_id": rec.action_id, "action_type": p.action_type, "target": p.target,
                                    "reason": str(e)})
                    actions.append(self.gateway.get(rec.action_id))
                    if fallback_to_l2:
                        p2 = ProposedAction(p.action_type, p.target, p.params, "L2", p.confidence,
                                            f"{p.rationale} (L3 refused: {e}; drafted for approval)", p.evidence,
                                            p.summary, p.finding_key)
                        rec = self.gateway.propose(f"{run_id}", spec, p2, inference_id=inf.inference_id,
                                                   needs_review=inf.needs_review,
                                                   review_subject=(inf.subject_type, inf.subject_id))
                    else:
                        continue
            actions.append(rec)

        incidents_out = []
        for inc in result.incidents:
            incident_id = f"INC-{uuid.uuid4().hex[:10].upper()}"
            self.store.insert("incident", {"incident_id": incident_id, "tenant_id": self.tenant_id, "source": agent_id,
                                           "severity": inc.severity, "title": inc.title, "status": "open",
                                           "opened_at": self.clock()})
            self.gateway.record_platform_action(run_id, spec, "incident.open", incident_id,
                                                {"key": inc.key, "tables": inc.tables, "owner": inc.owner,
                                                 "probable_cause": inc.probable_cause, "severity": inc.severity},
                                                inc.rationale)
            if inc.owner:
                self.gateway.record_platform_action(run_id, spec, "owner.notify", f"{incident_id}:{inc.owner}",
                                                    {"owner": inc.owner, "incident_id": incident_id}, inc.rationale)
            incidents_out.append({"incident_id": incident_id, **asdict(inc)})

        self._log_tool_calls(run_id, tools)
        output = {"findings": findings_out,
                  "actions": [{"action_id": a.action_id, "action_type": a.action_type, "target": a.target,
                               "autonomy": a.autonomy, "status": a.status} for a in actions],
                  "refused": refused, "incidents": incidents_out}
        self.store.insert("agent_run_log", {
            "run_id": run_id, "agent_id": agent_id, "tenant_id": self.tenant_id, "snapshot_ref": telemetry.ref,
            "rubric_version": self.rubrics.version,
            "inputs": {"trigger": trigger, "as_of": telemetry.as_of.isoformat(), "telemetry_ref": telemetry.ref,
                       "agent_version": impl.version, "tool_scope": list(spec.tool_scope)},
            "output": json_safe(output), "decision_summary": result.summary or f"{len(findings_out)} finding(s)",
            "recorded_at": self.clock()})
        self.store.update("agent_run", {"run_id": run_id}, {"status": "completed", "completed_at": self.clock()})
        return RunReport(run_id, agent_id, impl.version, self.tenant_id, telemetry.ref, findings_out, actions, refused,
                         incidents_out, len(tools.calls), result.summary)

    def _log_tool_calls(self, run_id: str, tools: ToolContext) -> None:
        now = self.clock()
        if tools.calls:
            self.store.insert("agent_tool_call", [
                {"run_id": run_id, "seq": c.seq, "tool": c.tool, "arguments": c.arguments, "tables_read": c.tables_read,
                 "rows_returned": c.rows_returned, "result_hash": c.result_hash, "called_at": now}
                for c in tools.calls])
