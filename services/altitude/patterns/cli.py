"""``altitude patterns`` — Pattern Library tools and the semantic-drift checker.

    altitude patterns scan --dialect teradata path.sql [--format text|json|md] [--min-confidence X] [--fail-on S1]
    altitude patterns profile --dialect oracle profile.json [--format ...]
    altitude patterns test [--dialect D] [--id TC-..] [-v]
    altitude patterns list [--dialect D]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _render(rep: dict, fmt: str) -> str:
    from .scan import render_json, render_md, render_text

    return {"json": render_json, "md": render_md, "text": render_text}[fmt](rep)


def _filter(hits, min_conf: float | None):
    from altitude.core.rubric import default_rubrics

    floor = min_conf if min_conf is not None else float(default_rubrics().get("rubric.patterns.scan.min_confidence_default"))
    return [h for h in hits if h.confidence >= floor]


def _fail(hits, fail_on: str | None) -> int:
    from .model import SEVERITY_ORDER

    if not fail_on:
        return 0
    return 1 if any(SEVERITY_ORDER[h.severity] <= SEVERITY_ORDER[fail_on] for h in hits) else 0


def _cmd_scan(args: argparse.Namespace) -> int:
    from .scan import Scanner, report

    scanner = Scanner()
    reports, code = [], 0
    for p in args.paths:
        path = Path(p)
        text = sys.stdin.read() if p == "-" else path.read_text(errors="replace")
        hits = _filter(scanner.scan_sql(text, args.dialect), args.min_confidence)
        code = max(code, _fail(hits, args.fail_on))
        reports.append(report(hits, args.dialect, source=str(p), scanner=scanner))
    if args.format == "json" and len(reports) > 1:
        sys.stdout.write(json.dumps(reports, indent=2) + "\n")
    else:
        for rep in reports:
            sys.stdout.write(_render(rep, args.format))
    return code


def _cmd_profile(args: argparse.Namespace) -> int:
    from .scan import Scanner, report

    scanner = Scanner()
    profile = json.loads(Path(args.path).read_text())
    hits = _filter(scanner.scan_profile(profile, args.dialect), args.min_confidence)
    sys.stdout.write(_render(report(hits, args.dialect, source=args.path, scanner=scanner), args.format))
    return _fail(hits, args.fail_on)


def _cmd_test(args: argparse.Namespace) -> int:
    from .golden import coverage_problems, run_all

    problems = coverage_problems()
    for p in problems:
        print(f"COVERAGE {p}")
    results = run_all(dialect=args.dialect, ids=args.id or None)
    failed = [r for r in results if not r.passed]
    for r in results:
        if args.verbose or not r.passed:
            print(f"{'PASS' if r.passed else 'FAIL'} {r.test_id} [{r.kind}] {r.issue_id}")
            for c in r.checks:
                if args.verbose or not c.ok:
                    print(f"    {'ok ' if c.ok else 'ERR'} {c.name}{': ' + c.detail if not c.ok else ''}")
    golden = sum(1 for r in results if r.kind == "golden")
    print(f"patterns test: {len(results) - len(failed)}/{len(results)} passed ({golden} golden), "
          f"{len(problems)} coverage problem(s)")
    return 1 if failed or problems else 0


def _cmd_list(args: argparse.Namespace) -> int:
    from .library import DIALECTS, default_library

    lib = default_library()
    for d in [args.dialect] if args.dialect else DIALECTS:
        print(f"== {d}")
        for i in lib.issues_for(d):
            print(f"  {i.id} [{i.severity}] {i.title}  (detector: {i.detection['detector']})")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("patterns", help="Pattern Library and semantic-drift checker")
    s = p.add_subparsers(dest="patterns_cmd", required=True)

    def common(sp):
        sp.add_argument("--dialect", required=True, help="teradata | oracle | sqlserver | netezza | redshift")
        sp.add_argument("--format", choices=["text", "json", "md"], default="text")
        sp.add_argument("--min-confidence", type=float, default=None)
        sp.add_argument("--fail-on", choices=["S1", "S2", "S3", "S4"], default=None,
                        help="exit 1 when a hit at or above this severity is found")

    scan = s.add_parser("scan", help="scan source code for semantic drift (Section 10.13 checklist)")
    common(scan)
    scan.add_argument("paths", nargs="+", help="source files ('-' for stdin)")
    scan.set_defaults(func=_cmd_scan)

    prof = s.add_parser("profile", help="run profile detectors over a metadata/statistics JSON file")
    common(prof)
    prof.add_argument("path")
    prof.set_defaults(func=_cmd_profile)

    test = s.add_parser("test", help="run golden, detector and profile tests from the Pattern Library")
    test.add_argument("--dialect")
    test.add_argument("--id", action="append", help="test case id (repeatable)")
    test.add_argument("-v", "--verbose", action="store_true")
    test.set_defaults(func=_cmd_test)

    ls = s.add_parser("list", help="list known issues")
    ls.add_argument("--dialect")
    ls.set_defaults(func=_cmd_list)
