"""``altitude agents ...`` — run, approve, execute, evaluate and promote fleet agents."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


def _store(path: str):
    from altitude.core.store import Store

    return Store(path)


def _telemetry(args: argparse.Namespace):
    from .telemetry import Telemetry

    tel = Telemetry.open(args.snapshot)
    return tel.at(args.as_of) if getattr(args, "as_of", None) else tel


def _executor(args: argparse.Namespace, tel: Any):
    if getattr(args, "live", False):
        from .executor import LiveExecutor

        try:
            import snowflake.connector  # type: ignore[import-not-found]
        except ImportError:
            raise SystemExit("--live needs the 'snowflake' extra: pip install 'altitude[snowflake]'")
        con = snowflake.connector.connect(
            account=os.environ["SNOWFLAKE_ACCOUNT"], user=os.environ["SNOWFLAKE_USER"],
            private_key_file=os.environ.get("SNOWFLAKE_PRIVATE_KEY_FILE"), role=os.environ.get("SNOWFLAKE_ROLE"),
            warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE"), authenticator=os.environ.get("SNOWFLAKE_AUTHENTICATOR",
                                                                                          "SNOWFLAKE_JWT"))
        return LiveExecutor(con, dry_run=args.dry_run)
    if getattr(args, "simulate", False):
        from .executor import SimulatedSnowflake

        return SimulatedSnowflake(tel)
    return None


def _print(obj: Any, as_json: bool) -> None:
    from altitude.core.store import json_safe

    if as_json:
        print(json.dumps(json_safe(obj), indent=2, sort_keys=True, default=str))
    else:
        print(obj)


def cmd_list(args: argparse.Namespace) -> int:
    from .catalogue import load_agent_catalogue

    for a in sorted(load_agent_catalogue().values(), key=lambda x: x.number):
        flag = "v1" if a.implemented else "--"
        print(f"{a.number:>2} {flag} {a.agent_id:<28} {a.max_autonomy}  {a.trigger['description']:<45} {a.service_user}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from .runtime import AgentRunner

    store = _store(args.store)
    tel = _telemetry(args)
    runner = AgentRunner(store, tenant_id=args.tenant)
    executor = _executor(args, tel)
    report = runner.run(args.agent, tel, trigger=args.trigger, executor=executor,
                        require_promoted=not args.allow_unpromoted)
    if args.json:
        _print(report.to_dict(), True)
        return 0
    print(f"{report.agent_id} {report.version} run {report.run_id} on {report.telemetry_ref}: {report.summary}")
    for f in report.findings:
        review = " [REVIEW]" if f["needs_review"] else ""
        print(f"  finding  {f['kind']:<20} {f['subject']:<32} conf={f['confidence']:.2f}{review}  {f['title']}")
    for a in report.actions:
        print(f"  action   {a.action_id} {a.autonomy} {a.status:<9} {a.action_type:<34} {a.target}")
    for r in report.refused:
        print(f"  refused  {r['action_id']} {r['reason']}")
    for i in report.incidents:
        print(f"  incident {i['incident_id']} {i['severity']} {i['title']}")
    if executor is not None and getattr(executor, "executed", None):
        print("  executed SQL:")
        for s in executor.executed:
            print(f"    {s};")
    return 0


def _gateway(args: argparse.Namespace):
    from .actions import ActionGateway
    from .catalogue import load_tenant_policy

    return ActionGateway(_store(args.store), load_tenant_policy(args.tenant))


def cmd_approve(args: argparse.Namespace) -> int:
    rec = _gateway(args).approve(args.action_id, args.approver, args.role, args.comment)
    print(f"{rec.action_id}: {rec.status} by {args.approver}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    rec = _gateway(args).reject(args.action_id, args.approver, args.role, args.comment)
    print(f"{rec.action_id}: {rec.status} by {args.approver}")
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    gw = _gateway(args)
    tel = _telemetry(args)
    executor = _executor(args, tel)
    if executor is None:
        raise SystemExit("choose an executor: --simulate (snapshot copy) or --live (DB-API connection)")
    rec = gw.execute(args.action_id, executor, tel)
    print(f"{rec.action_id}: {rec.status}")
    for s in executor.executed:
        print(f"  {s};")
    return 0


def cmd_guard(args: argparse.Namespace) -> int:
    gw = _gateway(args)
    tel = _telemetry(args)
    executor = _executor(args, tel)
    if executor is None:
        raise SystemExit("choose an executor: --simulate or --live")
    for r in gw.check_all_guards(tel, executor):
        verdict = "ROLLED BACK" if r.regressed else "ok"
        print(f"{r.action_id} {r.metric}: {r.baseline:.3f} -> {r.observed:.3f} (tolerance {r.tolerance}) {verdict}")
    return 0


def cmd_log(args: argparse.Namespace) -> int:
    from .actions import ActionLog

    rows = ActionLog(_store(args.store)).history(args.action_id)
    for r in rows:
        print(f"{r['seq']:>2} {r['recorded_at']} {r['status']:<11} {r['autonomy']} {r['actor']:<24} "
              f"{r['action_type']} {r['target']}")
    return 0 if rows else 1


def cmd_evals(args: argparse.Namespace) -> int:
    from .evals import promote, run_suite
    from .runtime import registry

    agents = [args.agent] if args.agent else sorted(registry())
    ok = True
    store = _store(args.store) if args.promote else None
    for aid in agents:
        rep = run_suite(aid)
        print(f"{aid} {rep.version}: {sum(c.passed for c in rep.cases)}/{len(rep.cases)} golden incidents passed")
        for c in rep.cases:
            if not c.passed:
                ok = False
                print(f"  FAIL {c.case_id}: {'; '.join(c.failures)}")
        if args.promote:
            from .errors import PromotionBlocked

            try:
                promote(store, rep, args.approver)
                print(f"  promoted {aid} {rep.version} (approver {args.approver})")
            except PromotionBlocked as e:
                ok = False
                print(f"  BLOCKED: {e}", file=sys.stderr)
    return 0 if ok else 1


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("agents", help="agent fleet: run, approve, execute, evaluate, promote")
    sub = p.add_subparsers(dest="agents_cmd", required=True)

    sub.add_parser("list", help="list the 16-agent catalogue").set_defaults(func=cmd_list)

    r = sub.add_parser("run", help="run an agent over a sealed snapshot")
    r.add_argument("agent")
    r.add_argument("--snapshot", required=True)
    r.add_argument("--store", default="altitude.duckdb", help="control-plane store (DuckDB file)")
    r.add_argument("--tenant", default="default")
    r.add_argument("--trigger", default="manual")
    r.add_argument("--as-of", dest="as_of")
    r.add_argument("--simulate", action="store_true", help="execute pre-approved L3 actions on a simulated copy")
    r.add_argument("--live", action="store_true", help="execute pre-approved L3 actions on the live account")
    r.add_argument("--dry-run", action="store_true", help="with --live: render and record SQL only")
    r.add_argument("--allow-unpromoted", action="store_true", help="run a version that has not passed its evals")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_run)

    for name, fn, helptext in (("approve", cmd_approve, "record a human approval for an L2 action"),
                               ("reject", cmd_reject, "record a human rejection for an L2 action")):
        a = sub.add_parser(name, help=helptext)
        a.add_argument("action_id")
        a.add_argument("--approver", required=True)
        a.add_argument("--role", help="approver's owner role (checked against tenant approvers)")
        a.add_argument("--comment")
        a.add_argument("--store", default="altitude.duckdb")
        a.add_argument("--tenant", default="default")
        a.set_defaults(func=fn)

    e = sub.add_parser("execute", help="execute an approved (L2) or pre-approved (L3) action")
    e.add_argument("action_id")
    e.add_argument("--snapshot", required=True)
    e.add_argument("--store", default="altitude.duckdb")
    e.add_argument("--tenant", default="default")
    e.add_argument("--simulate", action="store_true")
    e.add_argument("--live", action="store_true")
    e.add_argument("--dry-run", action="store_true")
    e.set_defaults(func=cmd_execute)

    gd = sub.add_parser("guard", help="re-check guard metrics of executed L3 actions; auto-rollback on regression")
    gd.add_argument("--snapshot", required=True, help="telemetry covering the post-change observation window")
    gd.add_argument("--store", default="altitude.duckdb")
    gd.add_argument("--tenant", default="default")
    gd.add_argument("--simulate", action="store_true")
    gd.add_argument("--live", action="store_true")
    gd.add_argument("--dry-run", action="store_true")
    gd.set_defaults(func=cmd_guard)

    lg = sub.add_parser("log", help="show the immutable history of one action")
    lg.add_argument("action_id")
    lg.add_argument("--store", default="altitude.duckdb")
    lg.set_defaults(func=cmd_log)

    ev = sub.add_parser("evals", help="run golden-incident eval suites (and optionally promote)")
    ev.add_argument("--agent")
    ev.add_argument("--promote", action="store_true")
    ev.add_argument("--approver", default="")
    ev.add_argument("--store", default="altitude.duckdb")
    ev.set_defaults(func=cmd_evals)
