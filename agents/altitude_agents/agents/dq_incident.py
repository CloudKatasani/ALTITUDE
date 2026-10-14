"""DQ Incident Agent (Section 18.2 #6, max L2): cluster DMF failures along lineage, find the probable
cause (failed load task, load errors, recent DDL), notify the owner, open an incident and draft a
quarantine. Guardrail: never deletes data (forbidden statements are enforced by the action gateway)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from ..actions import ProposedAction
from ..runtime import AgentContext, AgentResult, BaseAgent, Finding, Incident


class DQIncident(BaseAgent):
    agent_id = "AG-DQ-INCIDENT"
    version = "1.0.0"

    def run(self, ctx: AgentContext) -> AgentResult:
        lookback = float(ctx.r("dq_incident.lookback_days"))
        window = timedelta(hours=float(ctx.r("dq_incident.cause_window_hours")))
        violations = ctx.call("dq_violations", days=lookback)
        if not violations:
            return AgentResult(summary="no data metric violations in the lookback window")
        edges = ctx.call("table_lineage", days=float(ctx.r("dq_incident.lineage_days")))
        down: dict[str, set[str]] = defaultdict(set)
        for e in edges:
            down[e["UPSTREAM"]].add(e["DOWNSTREAM"])
        by_table: dict[str, list[dict]] = defaultdict(list)
        for v in violations:
            by_table[v["TABLE_NAME"]].append(v)
        tables = sorted(by_table)

        # ---- cluster violating tables connected by lineage (reachability in either direction)
        parent = {t: t for t in tables}

        def find(x: str) -> str:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        reach = {t: self._reachable(t, down) for t in tables}
        for a in tables:
            for b in tables:
                if a != b and b in reach[a]:
                    parent[find(b)] = find(a)
        clusters: dict[str, list[str]] = defaultdict(list)
        for t in tables:
            clusters[find(t)].append(t)

        task_targets = {e["UPSTREAM"]: e["DOWNSTREAM"] for e in edges if e["EVIDENCE"] == "task_target"}
        failures = ctx.call("task_failures", days=lookback + window.total_seconds() / 86400)
        load_errs = ctx.call("load_errors", days=lookback + window.total_seconds() / 86400)
        owners = {r["FQ_NAME"]: r["OWNER"] for r in ctx.call("table_owners")}
        tier1 = {r["FQ_NAME"] for r in ctx.call("tier1_tables")}

        findings, actions, incidents = [], [], []
        for members in sorted(clusters.values()):
            members = sorted(members)
            roots = [t for t in members if not any(t in reach[o] for o in members if o != t)] or members
            root = roots[0]
            first_seen: datetime = min(v["MEASUREMENT_TIME"] for t in members for v in by_table[t])
            cause, cause_ev = self._cause(ctx, root, first_seen, window, task_targets, failures, load_errs)
            if cause:
                conf = float(ctx.r("dq_incident.confidence_with_cause"))
            elif len(members) > 1:
                conf = float(ctx.r("dq_incident.confidence_lineage_only"))
                cause = f"origin at {root}; propagated downstream along lineage"
            else:
                conf = float(ctx.r("dq_incident.confidence_no_cause"))
                cause = "unknown — no failed load, load error or DDL found before the first violation"
            owner = owners.get(root) or next((owners[t] for t in members if t in owners), None)
            severity = ctx.r("dq_incident.severity_tier1" if any(t in tier1 for t in members)
                             else "dq_incident.severity_default")
            metrics = sorted({f"{t}:{v['METRIC_NAME']}" for t in members for v in by_table[t]})
            rationale = (f"{len(metrics)} DMF violation(s) on {len(members)} lineage-connected table(s) since "
                         f"{first_seen}; probable cause: {cause}")
            f = Finding(kind="dq_cluster", subject=root,
                        title=f"DQ incident: {', '.join(members)} ({len(metrics)} failing metric(s))",
                        confidence=conf, rationale=rationale,
                        detail={"tables": members, "origin": root, "metrics": metrics, "probable_cause": cause,
                                "cause_evidence": cause_ev, "owner": owner, "severity": severity,
                                "first_violation": first_seen},
                        evidence=[f"DATA_QUALITY_MONITORING_RESULTS:{m}" for m in metrics] + cause_ev)
            findings.append(f)
            incidents.append(Incident(key=f.key, severity=severity, title=f.title, owner=owner, tables=members,
                                      probable_cause=cause, confidence=conf, rationale=rationale))
            for t in members:
                actions.append(ProposedAction(
                    "table.quarantine", t, {"tag": ctx.policy.quarantine_tag,
                                            "reason": f"DQ incident {root}: {cause}"},
                    "L2", conf, f"Quarantine {t} until the owner confirms the fix: {rationale}", f.evidence,
                    f"Tag {t} {ctx.policy.quarantine_tag}='QUARANTINED' (hides it from consumers; no data deleted)",
                    f.key))
        return AgentResult(findings=findings, actions=actions, incidents=incidents,
                           summary=f"{len(incidents)} DQ incident(s) opened; {len(actions)} quarantine draft(s)")

    @staticmethod
    def _reachable(start: str, down: dict[str, set[str]]) -> set[str]:
        seen, stack = set(), list(down.get(start, ()))
        while stack:
            n = stack.pop()
            if n not in seen:
                seen.add(n)
                stack.extend(down.get(n, ()))
        return seen

    @staticmethod
    def _cause(ctx: AgentContext, table: str, first_seen: datetime, window: timedelta, task_targets: dict,
               failures: list[dict], load_errs: list[dict]) -> tuple[str | None, list[str]]:
        loaders = {task for task, tgt in task_targets.items() if tgt == table}
        failed = [f for f in failures if f["FQ_NAME"] in loaders
                  and first_seen - window <= f["SCHEDULED_TIME"] <= first_seen]
        if failed:
            last = failed[-1]
            return (f"load task {last['FQ_NAME']} failed at {last['SCHEDULED_TIME']}: {last['ERROR_MESSAGE']}",
                    [f"TASK_HISTORY:{x['RUN_ID']}" for x in failed])
        errs = [e for e in load_errs if e["TABLE_NAME"] == table and first_seen - window <= e["LAST_LOAD_TIME"] <= first_seen]
        if errs:
            return (f"{sum(int(e['ERROR_COUNT'] or 0) for e in errs)} load error(s) in {len(errs)} file(s) loaded into "
                    f"{table}", [f"COPY_HISTORY:{e['FILE_NAME']}" for e in errs])
        ddl = ctx.call("recent_ddl", objects=[table], before=first_seen, hours=window.total_seconds() / 3600)
        if ddl:
            d = ddl[-1]
            return (f"{d['QUERY_TYPE']} on {table} by {d['USER_NAME']} at {d['START_TIME']}",
                    [f"QUERY_HISTORY:{x['QUERY_ID']}" for x in ddl])
        return None, []
