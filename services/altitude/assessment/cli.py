"""``altitude assess`` — run an assessment, export reports, list the review queue."""

from __future__ import annotations

import argparse
import json


def _store(path: str | None):
    if not path:
        return None
    from altitude.core.store import Store

    return Store(path)


def _cmd_run(args: argparse.Namespace) -> int:
    from altitude.core.errors import AppendOnlyViolation

    from .engine import run_assessment
    from .report import export_report

    try:
        result = run_assessment(args.harvest, args.out, store=_store(args.store), snapshot_id=args.snapshot_id)
    except AppendOnlyViolation as e:
        print(json.dumps({"error": str(e)}))
        return 1
    out = {"snapshot_id": result.snapshot_id, "path": str(result.snapshot.path),
           "content_hash": result.snapshot.content_hash, "rubric_version": result.rubric_version,
           "dispositions": result.summary["dispositions"], "review_items": result.summary["review_items"],
           "drift_scan": result.summary["drift_scan"]["status"]}
    if args.report:
        out["report"] = {k: str(v) for k, v in export_report(result, args.report).items()}
    print(json.dumps(out, indent=2))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from .report import export_report

    paths = export_report(args.snapshot, args.out, theme=args.theme)
    print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    from altitude.core.ai import ReviewQueue

    store = _store(args.store)
    q = ReviewQueue(store)
    if args.decide:
        q.decide(args.decide, args.reviewer, args.decision, args.comment)
    items = q.open_items("object_disposition")
    print(json.dumps([{k: v for k, v in i.items() if k in {"item_id", "subject_id", "reason", "confidence"}}
                      for i in items], indent=2, default=str))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("assess", help="assessment engine: dispositions, complexity, anti-patterns, drift risk")
    s = p.add_subparsers(dest="assess_cmd", required=True)

    r = s.add_parser("run", help="assess a sealed harvest snapshot and seal the assessment snapshot")
    r.add_argument("--harvest", required=True, help="harvest snapshot .duckdb path")
    r.add_argument("--out", required=True, help="directory for the assessment snapshot")
    r.add_argument("--store", help="control-plane DuckDB store (review queue, dispositions)")
    r.add_argument("--snapshot-id")
    r.add_argument("--report", help="also export Markdown/HTML/CSV to this directory")
    r.set_defaults(func=_cmd_run)

    e = s.add_parser("report", help="export the report and CSV inventory from an assessment snapshot")
    e.add_argument("--snapshot", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--theme")
    e.set_defaults(func=_cmd_report)

    v = s.add_parser("review", help="list (or decide) open disposition review items")
    v.add_argument("--store", required=True)
    v.add_argument("--decide", metavar="ITEM_ID")
    v.add_argument("--reviewer")
    v.add_argument("--decision", choices=["approved", "rejected", "modified"])
    v.add_argument("--comment")
    v.set_defaults(func=_cmd_review)
