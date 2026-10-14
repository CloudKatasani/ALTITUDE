"""``altitude airready ...`` — EAIRN readiness score, semantic views, Cortex templates and eval harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_score(args: argparse.Namespace) -> int:
    from altitude.core.snapshot import Snapshot

    from . import scoring

    report = scoring.score(Snapshot.open(args.snapshot, verify=True))
    if args.store:
        from altitude.core.store import Store

        scoring.persist(Store(args.store), report)
    if args.markdown:
        Path(args.markdown).write_text(scoring.to_markdown(report))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"{report.snapshot_id}: EAIRN {report.overall}/100 — level {report.maturity_level} "
          f"({report.maturity_label}); score {report.score_hash}")
    for p, v in report.pillars.items():
        print(f"  {p:<16} {v['score'] if v['score'] is not None else 'n/a':>6}  {v['passed']}/{v['applicable']} passed")
    for r in report.priorities[:10]:
        print(f"  gap {r['check_id']:<12} {r['title']} ({r['score']} < {r['pass_mark']}) -> {r['playbook']}")
    return 0


def cmd_semantic_views(args: argparse.Namespace) -> int:
    from altitude.core.errors import KnowledgeValidationError

    from . import kpi_registry

    try:
        if args.registry:
            text = Path(args.registry).read_text()
            reg = kpi_registry.from_text(text, rel=args.registry)
        else:
            reg = kpi_registry.load()
    except KnowledgeValidationError as e:
        for p in e.problems:
            print(p, file=sys.stderr)
        return 1
    for domain, ddl in kpi_registry.semantic_views(reg).items():
        print(f"-- {domain}\n{ddl}")
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    from . import harness

    report = harness.run()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True, default=str))
    else:
        for r in report.results:
            print(f"  {'PASS' if r.passed else 'FAIL'} {r.question_id} {r.question}" + (f" — {r.reason}" if r.reason else ""))
        for p in report.golden_integrity:
            print(f"  GOLDEN {p}")
        print(f"eval score {report.score} (min {report.pass_rate_min}): {'PASS' if report.passed else 'FAIL'}")
    return 0 if report.passed else 1


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("airready", help="AI-Ready: EAIRN score, semantic views, Cortex templates, eval harness")
    sub = p.add_subparsers(dest="airready_cmd", required=True)
    s = sub.add_parser("score", help="EAIRN 8-pillar readiness score for a sealed snapshot")
    s.add_argument("--snapshot", required=True)
    s.add_argument("--json", action="store_true")
    s.add_argument("--markdown")
    s.add_argument("--store")
    s.set_defaults(func=cmd_score)
    v = sub.add_parser("semantic-views", help="render CREATE SEMANTIC VIEW DDL (one definition per KPI enforced)")
    v.add_argument("--registry", help="alternative KPI registry YAML to validate/render")
    v.set_defaults(func=cmd_semantic_views)
    e = sub.add_parser("eval", help="run the golden-question evaluation harness")
    e.add_argument("--json", action="store_true")
    e.set_defaults(func=cmd_eval)
