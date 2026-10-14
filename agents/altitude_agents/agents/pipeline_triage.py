"""Pipeline Triage (Section 18.2 #4): classify task failures from error text and recent changes; rerun
idempotent tasks at L3 for transient causes (idempotency flag as data), otherwise draft a fix (L2)."""

from __future__ import annotations

import re
from collections import defaultdict

from ..actions import ProposedAction
from ..catalogue import load_error_signatures
from ..runtime import AgentContext, AgentResult, BaseAgent, Finding


class PipelineTriage(BaseAgent):
    agent_id = "AG-PIPELINE-TRIAGE"
    version = "1.0.0"

    def __init__(self, signatures: list[dict] | None = None):
        self.signatures = signatures if signatures is not None else load_error_signatures()

    def classify(self, error: str | None) -> dict | None:
        text = error or ""
        for sig in self.signatures:
            if re.search(sig["pattern"], text, re.IGNORECASE):
                return sig
        return None

    def run(self, ctx: AgentContext) -> AgentResult:
        days = float(ctx.r("pipeline_triage.lookback_days"))
        change_hours = float(ctx.r("pipeline_triage.recent_change_hours"))
        failures = ctx.call("task_failures", days=days)
        if not failures:
            return AgentResult(summary="no task failures in the lookback window")
        tasks = {t["FQ_NAME"]: t for t in ctx.call("task_definitions")}
        flagged = {t.upper() for t in ctx.policy.idempotent_tasks}
        flagged |= {r["FQ_NAME"].upper() for r in ctx.call("task_idempotency") if str(r["TAG_VALUE"]).lower() == "true"}
        children: dict[str, list[str]] = defaultdict(list)
        for t in tasks.values():
            for pred in str(t.get("PREDECESSORS") or "").split(","):
                if pred.strip():
                    children[pred.strip()].append(t["FQ_NAME"])

        by_task: dict[str, list[dict]] = defaultdict(list)
        for f in failures:
            by_task[f["FQ_NAME"]].append(f)
        findings, actions = [], []
        for fq in sorted(by_task):
            runs = by_task[fq]
            last = runs[-1]
            sig = self.classify(last["ERROR_MESSAGE"])
            target = (tasks.get(fq) or {}).get("TARGET_TABLE")
            ddl = ctx.call("recent_ddl", objects=[o for o in (fq, target) if o], before=last["SCHEDULED_TIME"],
                           hours=change_hours)
            downstream = self._downstream(fq, children)
            root = sig["root_cause"] if sig else "unclassified"
            conf = float(sig["confidence"]) if sig else float(ctx.r("pipeline_triage.confidence_unclassified"))
            reasons = [f"error {last['ERROR_CODE'] or ''} matched signature {sig['id']}" if sig
                       else f"error text did not match any known signature: {last['ERROR_MESSAGE']!r}"]
            if ddl:
                conf = min(float(ctx.r("pipeline_triage.confidence_cap")),
                           conf + float(ctx.r("pipeline_triage.confidence_recent_change_bonus")))
                reasons.append("recent DDL before the failure: " + "; ".join(
                    f"{d['QUERY_TYPE']} by {d['USER_NAME']} at {d['START_TIME']}" for d in ddl))
            idempotent = fq.upper() in flagged
            f = Finding(
                kind="root_cause", subject=fq,
                title=f"{fq}: {root} ({len(runs)} failure(s) in {int(days)}d, latest {last['SCHEDULED_TIME']})",
                confidence=round(conf, 3), rationale="; ".join(reasons),
                detail={"root_cause": root, "signature": sig["id"] if sig else None,
                        "retryable": bool(sig and sig["retryable"]), "failures": len(runs),
                        "latest_state": last["LATEST_STATE"], "error": last["ERROR_MESSAGE"],
                        "recent_changes": [d["QUERY_ID"] for d in ddl], "downstream_impact": downstream,
                        "idempotent": idempotent, "target_table": target},
                evidence=[f"TASK_HISTORY:{r['RUN_ID']}" for r in runs] + [f"QUERY_HISTORY:{d['QUERY_ID']}" for d in ddl])
            findings.append(f)
            still_failing = last["LATEST_STATE"] == "FAILED"
            if sig and sig["retryable"]:
                if still_failing:
                    actions.append(ProposedAction(
                        "task.rerun", fq, {}, "L3" if idempotent else "L2", f.confidence,
                        f"{f.rationale}; transient cause, task {'is' if idempotent else 'is NOT'} flagged idempotent",
                        f.evidence, f"EXECUTE TASK {fq}", f.key))
            else:
                fix = sig["fix"] if sig else "Unclassified failure: inspect the task query profile and error log."
                actions.append(ProposedAction(
                    "task.fix_draft", fq, {"fix": fix}, "L2", f.confidence, f.rationale, f.evidence,
                    f"Fix draft for {fq}: {fix}", f.key))
        return AgentResult(findings=findings, actions=actions,
                           summary=f"{len(findings)} failing task(s) triaged; {len(actions)} action(s) drafted")

    @staticmethod
    def _downstream(fq: str, children: dict[str, list[str]]) -> list[str]:
        out, stack = [], list(children.get(fq, []))
        while stack:
            t = stack.pop()
            if t not in out:
                out.append(t)
                stack.extend(children.get(t, []))
        return sorted(out)

