"""``altitude conversion`` - conversion orchestrator commands (M5)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_DB = ".altitude/altitude.duckdb"


def _store(args: argparse.Namespace):
    from altitude.core.store import Store

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    return Store(args.db)


def _print(obj) -> None:
    from altitude.core.store import json_safe

    print(json.dumps(json_safe(obj), indent=2, default=str))


def _cmd_tool(args: argparse.Namespace) -> int:
    from .orchestrator import select_converter
    from .snowconvert import SnowConvertCLI

    conv = select_converter(SnowConvertCLI(args.snowconvert))
    version = conv.version() if callable(getattr(conv, "version", None)) else conv.version
    _print({"converter": conv.name, "version": version})
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    from .orchestrator import ConversionOrchestrator, select_converter
    from .remediation import RemediationAgent
    from .snowconvert import SnowConvertCLI

    store = _store(args)
    conv = select_converter(SnowConvertCLI(args.snowconvert))
    orch = ConversionOrchestrator(store, args.engagement, converter=conv, source_system_id=args.source_system)
    result = orch.run(Path(args.source), args.dialect, Path(args.out))
    summary = {"run_id": result.run_id, "tool": result.tool, "tool_version": result.tool_version,
               "artifacts": result.artifact_ids, "issues": result.issue_count, "output": str(result.output_dir)}
    if args.remediate:
        agent = RemediationAgent(store, packs_root=Path(args.out) / result.run_id / "pr_packs")
        summary["pr_packs"] = {a: str(agent.remediate(a).pack_dir) for a in result.artifact_ids}
    _print(summary)
    return 0


def _cmd_parse_report(args: argparse.Namespace) -> int:
    from .snowconvert import parse_assessment_csv, parse_issues_csv

    text = Path(args.report).read_text(encoding="utf-8-sig")
    rows = parse_assessment_csv(text) if args.assessment else [i.to_dict() for i in parse_issues_csv(text)]
    _print(rows)
    return 0


def _cmd_remediate(args: argparse.Namespace) -> int:
    from altitude.core.ai import provider_for

    from .remediation import RemediationAgent

    store = _store(args)
    policy = json.loads(args.llm_policy) if args.llm_policy else None
    agent = RemediationAgent(store, packs_root=Path(args.packs), provider=provider_for(policy))
    res = agent.remediate(args.artifact)
    _print({"pack_id": res.pack_id, "pack_dir": str(res.pack_dir),
            "changes": [{"change_id": c.change_id, "rules": c.rule_ids, "confidence": c.confidence,
                         "below_review_floor": c.below_floor} for c in res.changes],
            "unresolved_issue_ids": res.unresolved_issue_ids})
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    from .review import ReviewWorkflow

    modified = Path(args.modified_file).read_text() if args.modified_file else None
    ReviewWorkflow(_store(args)).decide_change(args.change, args.reviewer, args.decision, args.comment, modified)
    print(f"{args.change}: {args.decision} by {args.reviewer}")
    return 0


def _cmd_accept(args: argparse.Namespace) -> int:
    from .review import ReviewWorkflow

    ReviewWorkflow(_store(args)).accept_issue(args.issue, args.reviewer, args.justification)
    print(f"{args.issue}: accepted by {args.reviewer}")
    return 0


def _cmd_review_artifact(args: argparse.Namespace) -> int:
    from .review import ReviewWorkflow

    ReviewWorkflow(_store(args)).review_artifact(args.artifact, args.reviewer, args.decision, args.comment)
    print(f"{args.artifact}: {args.decision} by {args.reviewer}")
    return 0


def _cmd_test(args: argparse.Namespace) -> int:
    from .review import ReviewWorkflow

    report = ReviewWorkflow(_store(args)).run_unit_tests(args.artifact)
    _print(report)
    return 0 if not report["failures"] else 1


def _cmd_gate(args: argparse.Namespace) -> int:
    from .review import ReviewWorkflow

    res = ReviewWorkflow(_store(args)).gate(args.artifact)
    _print({"gate": res.gate, "passed": res.passed, "metrics": res.metrics, "failures": res.failures,
            "rubric_version": res.rubric_version})
    return 0 if res.passed else 1


def _cmd_promote(args: argparse.Namespace) -> int:
    from altitude.core.errors import ApprovalRequired

    from .review import ReviewWorkflow

    try:
        art = ReviewWorkflow(_store(args)).promote(args.artifact, args.by)
    except ApprovalRequired as e:
        print(str(e), file=sys.stderr)
        return 1
    _print({"artifact_id": art["artifact_id"], "status": art["status"], "promoted_by": art["promoted_by"],
            "promoted_at": art["promoted_at"]})
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from . import factory

    store = _store(args)
    where, params = ("WHERE a.run_id=?", [args.run]) if args.run else ("", [])
    rows = store.query(
        "SELECT a.artifact_id, a.object_id, a.target_path, a.status, a.promoted_by, "
        "(SELECT count(*) FROM conversion_issue i WHERE i.artifact_id=a.artifact_id AND i.status='open') AS open_issues "
        f"FROM converted_artifact a {where} ORDER BY a.target_path", params)
    for r in rows:
        r["factory_state"] = factory.current_state(store, r["object_id"])
    _print(rows)
    return 0


def register(subparsers) -> None:
    p = subparsers.add_parser("conversion", help="conversion orchestrator (SnowConvert AI / sqlglot, AI remediation, review)")
    sub = p.add_subparsers(dest="conversion_cmd", required=True)

    def db(sp):
        sp.add_argument("--db", default=DEFAULT_DB, help=f"control-plane store (default {DEFAULT_DB})")
        return sp

    t = sub.add_parser("tool", help="show which converter will be used")
    t.add_argument("--snowconvert", help="SnowConvert AI CLI binary (default: $ALTITUDE_SNOWCONVERT_BIN or PATH)")
    t.set_defaults(func=_cmd_tool)

    r = db(sub.add_parser("run", help="convert a source directory"))
    r.add_argument("source")
    r.add_argument("--dialect", required=True, help="teradata|oracle|tsql")
    r.add_argument("--out", required=True)
    r.add_argument("--engagement", default="ENG-LOCAL")
    r.add_argument("--source-system", default="source")
    r.add_argument("--snowconvert", help="SnowConvert AI CLI binary")
    r.add_argument("--remediate", action="store_true", help="run the remediation agent and write PR packs")
    r.set_defaults(func=_cmd_run)

    pr = sub.add_parser("parse-report", help="parse a SnowConvert Issues.csv / TopLevelCodeUnits.csv report")
    pr.add_argument("report")
    pr.add_argument("--assessment", action="store_true")
    pr.set_defaults(func=_cmd_parse_report)

    rm = db(sub.add_parser("remediate", help="AI remediation -> PR pack for one artifact"))
    rm.add_argument("artifact")
    rm.add_argument("--packs", required=True, help="directory for PR packs (never a production location)")
    rm.add_argument("--llm-policy", help='tenant LLM policy JSON, e.g. {"provider": "cortex"} (default offline)')
    rm.set_defaults(func=_cmd_remediate)

    rv = db(sub.add_parser("review", help="record a reviewer decision on an AI change"))
    rv.add_argument("--change", required=True)
    rv.add_argument("--reviewer", required=True)
    rv.add_argument("--decision", required=True, choices=["approved", "rejected", "modified"])
    rv.add_argument("--comment")
    rv.add_argument("--modified-file", help="file holding the reviewer's replacement text (decision=modified)")
    rv.set_defaults(func=_cmd_review)

    ac = db(sub.add_parser("accept", help="accept an unresolved issue with a justification"))
    ac.add_argument("--issue", required=True)
    ac.add_argument("--reviewer", required=True)
    ac.add_argument("--justification", required=True)
    ac.set_defaults(func=_cmd_accept)

    ra = db(sub.add_parser("review-artifact", help="peer review of a whole artifact"))
    ra.add_argument("artifact")
    ra.add_argument("--reviewer", required=True)
    ra.add_argument("--decision", required=True, choices=["approved", "rejected", "modified"])
    ra.add_argument("--comment")
    ra.set_defaults(func=_cmd_review_artifact)

    te = db(sub.add_parser("test", help="run the PR pack's generated unit tests on the final content"))
    te.add_argument("artifact")
    te.set_defaults(func=_cmd_test)

    g = db(sub.add_parser("gate", help="evaluate the convert_exit gate for an artifact"))
    g.add_argument("artifact")
    g.set_defaults(func=_cmd_gate)

    pm = db(sub.add_parser("promote", help="promote an artifact (requires the convert_exit gate)"))
    pm.add_argument("artifact")
    pm.add_argument("--by", required=True, help="named approver recorded as promoted_by")
    pm.set_defaults(func=_cmd_promote)

    st = db(sub.add_parser("status", help="artifacts with factory state and open issues"))
    st.add_argument("--run")
    st.set_defaults(func=_cmd_status)
