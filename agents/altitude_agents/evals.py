"""Agent evaluation suites (golden incidents) and promotion gating (Section 18.3).

Each ``knowledge/agents/evals/<agent>.yaml`` lists golden incidents: a telemetry fixture (a synthetic
estate spec, optional appended rows, or explicit tables), an optional ``as_of`` / tenant, and the expected
findings, actions and incidents (plus ones that must be absent). ``run_suite`` executes the agent on every
case in an isolated in-memory store (no executor: decisions are evaluated, nothing is executed).

``promote`` records the results and an ``agent_version`` row whose ``eval_passed`` gates the runner:
a version is promoted only when the pass rate meets ``rubric.agents.promotion.eval_pass_rate_min``, no
golden case passed by the previously promoted version regresses, and a named human approves.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from altitude.core.errors import ApprovalRequired
from altitude.core.ids import canonical_json
from altitude.core.knowledge import load_yaml
from altitude.core.paths import knowledge_dir
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import Store, json_safe

from .catalogue import load_tenant_policy
from .errors import PromotionBlocked
from .runtime import AgentRunner, BaseAgent, RunReport, registry
from .telemetry import Telemetry

PASS_RATE_REF = "rubric.agents.promotion.eval_pass_rate_min"
_TELEMETRY_CACHE: dict[str, Telemetry] = {}


def suite_path(agent_id: str, root: Path | None = None) -> Path:
    root = root or knowledge_dir()
    for p in sorted((root / "agents" / "evals").glob("*.yaml")):
        if (load_yaml(p.relative_to(root).as_posix(), root) or {}).get("agent_id") == agent_id:
            return p
    raise FileNotFoundError(f"no eval suite for {agent_id}")


def load_suite(agent_id: str, root: Path | None = None) -> dict:
    root = root or knowledge_dir()
    return load_yaml(suite_path(agent_id, root).relative_to(root).as_posix(), root)


# --------------------------------------------------------------------------- fixtures
def _synthetic_tables(spec: dict) -> dict[str, list[dict]]:
    from altitude.synthetic import AccountSpec, generate

    kwargs: dict[str, Any] = {}
    for k in ("profile", "days", "seed", "account_name"):
        if k in spec:
            kwargs[k] = spec[k]
    if "end_date" in spec:
        kwargs["end_date"] = date.fromisoformat(str(spec["end_date"]))
    if "disabled_issues" in spec:
        kwargs["disabled_issues"] = set(spec["disabled_issues"])
    if "anomalies" in spec:
        kwargs["anomalies"] = [{"date": date.fromisoformat(str(a["date"])), "warehouse": a["warehouse"],
                                "factor": float(a["factor"])} for a in spec["anomalies"]]
    return generate(AccountSpec(**kwargs)).tables


def case_telemetry(case: dict) -> Telemetry:
    t = case["telemetry"]
    key = canonical_json({k: t.get(k) for k in ("synthetic", "append", "tables")})
    tel = _TELEMETRY_CACHE.get(key)
    if tel is None:
        if "tables" in t:
            tables = {k: list(v) for k, v in t["tables"].items()}
        else:
            tables = _synthetic_tables(t.get("synthetic") or {})
            for name, rows in (t.get("append") or {}).items():
                tables[name] = list(tables.get(name, [])) + list(rows)
        tel = Telemetry.from_tables(tables, as_of=None)
        _TELEMETRY_CACHE[key] = tel
    return tel.at(str(t["as_of"])) if t.get("as_of") else tel


# --------------------------------------------------------------------------- matching
def _match(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict) and set(expected) == {"between"}:
        lo, hi = expected["between"]
        return isinstance(actual, (int, float)) and lo <= actual <= hi
    if isinstance(expected, dict) and set(expected) == {"contains"}:
        return isinstance(actual, str) and str(expected["contains"]).lower() in actual.lower()
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(k in actual and _match(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list):
            return False
        return all(any(_match(a, e) for a in actual) for e in expected)
    if isinstance(actual, float) and isinstance(expected, (int, float)):
        return abs(actual - expected) < 1e-9  # threshold-ok: float equality epsilon, not a tunable
    return actual == expected


def _action_view(report: RunReport) -> list[dict]:
    return [{"action_type": a.action_type, "target": a.target, "autonomy": a.autonomy, "status": a.status,
             "params": a.payload.get("params", {})} for a in report.actions if a.status != "rejected"]


@dataclass
class CaseResult:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    agent_id: str
    version: str
    cases: list[CaseResult]

    @property
    def pass_rate(self) -> float:
        return sum(c.passed for c in self.cases) / len(self.cases) if self.cases else 0.0

    @property
    def passed_ids(self) -> set[str]:
        return {c.case_id for c in self.cases if c.passed}

    def to_dict(self) -> dict:
        return {"agent_id": self.agent_id, "version": self.version, "pass_rate": self.pass_rate,
                "cases": [{"case_id": c.case_id, "passed": c.passed, "failures": c.failures} for c in self.cases]}


def check_case(case: dict, report: RunReport) -> list[str]:
    exp = case.get("expect", {})
    findings = json_safe(report.findings)
    actions = json_safe(_action_view(report))
    incidents = json_safe(report.incidents)
    problems = []
    for e in exp.get("findings", []):
        if not any(_match(f, e) for f in findings):
            problems.append(f"missing finding {e}")
    for e in exp.get("absent_findings", []):
        hit = [f"{f['kind']}:{f['subject']}" for f in findings if _match(f, e)]
        if hit:
            problems.append(f"unexpected finding(s) {hit} matching {e}")
    for e in exp.get("actions", []):
        if not any(_match(a, e) for a in actions):
            problems.append(f"missing action {e}")
    for e in exp.get("absent_actions", []):
        hit = [f"{a['action_type']}:{a['target']}" for a in actions if _match(a, e)]
        if hit:
            problems.append(f"unexpected action(s) {hit} matching {e}")
    for e in exp.get("incidents", []):
        if not any(_match(i, e) for i in incidents):
            problems.append(f"missing incident {e}")
    if "max_findings" in exp and len(findings) > int(exp["max_findings"]):
        problems.append(f"{len(findings)} findings > max {exp['max_findings']}")
    if "max_actions" in exp and len(actions) > int(exp["max_actions"]):
        problems.append(f"{len(actions)} actions > max {exp['max_actions']}")
    return problems


def run_case(agent_id: str, case: dict, agent: BaseAgent | None = None, rubrics: RubricSet | None = None) -> CaseResult:
    store = Store()
    tenant = case.get("tenant", "default")
    policy = load_tenant_policy(tenant, overrides=case.get("policy_overrides"))
    runner = AgentRunner(store, tenant_id=tenant, rubrics=rubrics, policy=policy)
    impl = agent or registry()[agent_id]()
    try:
        report = runner.run(agent_id, case_telemetry(case), trigger=f"eval:{case['id']}", agent=impl,
                            require_promoted=False)
    except Exception as e:  # noqa: BLE001 - a crashing agent fails the case
        return CaseResult(case["id"], False, [f"agent raised {type(e).__name__}: {e}"])
    problems = check_case(case, report)
    return CaseResult(case["id"], not problems, problems)


def run_suite(agent_id: str, agent: BaseAgent | None = None, rubrics: RubricSet | None = None,
              root: Path | None = None) -> EvalReport:
    suite = load_suite(agent_id, root)
    impl = agent or registry()[agent_id]()
    results = [run_case(agent_id, c, impl, rubrics) for c in suite["cases"]]
    return EvalReport(agent_id, impl.version, results)


# --------------------------------------------------------------------------- promotion
def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def promote(store: Store, report: EvalReport, approver: str, rubrics: RubricSet | None = None,
            prompt_template: str | None = None) -> None:
    """Record eval results and promote ``report.version`` — or raise :class:`PromotionBlocked`."""
    rubrics = rubrics or default_rubrics()
    if not approver:
        raise ApprovalRequired("promotion needs a named human approver")
    now = _now()
    previous = store.query("SELECT version FROM agent_version WHERE agent_id = ? AND eval_passed AND version <> ? "
                           "ORDER BY released_at DESC LIMIT 1", [report.agent_id, report.version])
    regressions: list[str] = []
    if previous:
        prev_passed = {r["case_id"] for r in store.query(
            "SELECT case_id FROM agent_eval_result WHERE agent_id = ? AND version = ? AND passed",
            [report.agent_id, previous[0]["version"]])}
        regressions = sorted(prev_passed - report.passed_ids)
    store.insert("agent_eval_result", [
        {"agent_id": report.agent_id, "version": report.version, "case_id": c.case_id, "passed": c.passed,
         "details": {"failures": c.failures}, "evaluated_at": now} for c in report.cases])
    minimum = float(rubrics.get(PASS_RATE_REF))
    passed = report.pass_rate >= minimum and not regressions and bool(report.cases)
    row = {"agent_id": report.agent_id, "version": report.version, "prompt_template": prompt_template,
           "eval_passed": passed, "released_at": now}
    if store.get("agent_version", agent_id=report.agent_id, version=report.version):
        store.update("agent_version", {"agent_id": report.agent_id, "version": report.version},
                     {"eval_passed": passed, "released_at": now})
    else:
        store.insert("agent_version", row)
    store.insert("approval", {"approval_id": f"APR-{uuid.uuid4().hex[:12].upper()}", "subject_type": "agent_version",
                              "subject_id": f"{report.agent_id}@{report.version}", "approver": approver,
                              "decision": "approved" if passed else "rejected",
                              "comment": json.dumps({"pass_rate": report.pass_rate, "regressions": regressions}),
                              "decided_at": now})
    if not passed:
        failing = [f"{c.case_id}: {'; '.join(c.failures)}" for c in report.cases if not c.passed]
        raise PromotionBlocked(
            f"{report.agent_id} {report.version} not promoted: pass rate {report.pass_rate:.2f} (min {minimum})"
            + (f"; regressions vs {previous[0]['version']}: {regressions}" if regressions else "")
            + ("\n  " + "\n  ".join(failing) if failing else ""))
