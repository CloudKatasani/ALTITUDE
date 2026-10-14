"""``altitude knowledge-publish`` — publish knowledge YAML into the canonical tables.

    altitude knowledge-publish load --db store.duckdb
    altitude knowledge-publish render --out DIR      (write this module's renderings elsewhere, e.g. for review)
    altitude knowledge-publish stats
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _cmd_load(args) -> int:
    from altitude.core.store import Store

    from .load import publish

    res = publish(Store(args.db))
    print(json.dumps(res.as_dict(), indent=2))
    return 0


def _cmd_render(args) -> int:
    from .generate import generate

    out = Path(args.out)
    for rel, content in sorted(generate().items()):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        print(f"wrote {p}")
    return 0


def _cmd_stats(args) -> int:
    from altitude.patterns.golden import coverage_problems
    from altitude.patterns.library import default_library

    lib = default_library()
    sev: dict[str, int] = {}
    for i in lib.issues.values():
        sev[i.severity] = sev.get(i.severity, 0) + 1
    print(json.dumps({
        "version": lib.version, "known_issues": len(lib.issues), "by_severity": dict(sorted(sev.items())),
        "mappings": len(lib.mappings), "test_cases": len(lib.tests),
        "golden_tests": sum(1 for t in lib.tests.values() if t["kind"] == "golden"),
        "coverage_problems": coverage_problems(lib),
    }, indent=2))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("knowledge-publish", help="publish the Pattern Library and rubrics into canonical tables")
    s = p.add_subparsers(dest="kp_cmd", required=True)
    ld = s.add_parser("load", help="validate and load knowledge YAML into a canonical store")
    ld.add_argument("--db", required=True)
    ld.set_defaults(func=_cmd_load)
    rd = s.add_parser("render", help="write the knowledge_publish renderings to a directory")
    rd.add_argument("--out", required=True)
    rd.set_defaults(func=_cmd_render)
    st = s.add_parser("stats", help="Pattern Library statistics and coverage problems")
    st.set_defaults(func=_cmd_stats)
