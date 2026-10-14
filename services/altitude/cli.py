"""``altitude`` command line.

Core commands live here; each module contributes a sub-command group through
``altitude.<module>.cli.register(subparsers)`` (see ``MODULE_CLIS``).
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys

MODULE_CLIS = [
    "altitude.knowledge_publish.cli",
    "altitude.patterns.cli",
    "altitude.synthetic.cli",
    "altitude.diagnostics.cli",
    "altitude.observability.cli",
    "altitude.foundation.cli",
    "altitude_agents.cli",
    "altitude_connectors.cli",
    "altitude.assessment.cli",
    "altitude.planning.cli",
    "altitude.conversion.cli",
    "altitude.validation.cli",
    "altitude.etl.cli",
    "altitude.airready.cli",
    "altitude.api.cli",
    "altitude.mcp.cli",
]


def _cmd_validate(args: argparse.Namespace) -> int:
    from altitude.core.knowledge import validate_tree

    problems = validate_tree()
    for p in problems:
        print(p, file=sys.stderr)
    print(f"knowledge: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from altitude.core import generated

    if args.check:
        problems = generated.diff()
        for p in problems:
            print(p, file=sys.stderr)
        print(f"generated: {'OK' if not problems else f'{len(problems)} problem(s)'}")
        return 1 if problems else 0
    for rel in generated.write_all():
        print(f"wrote generated/{rel}")
    return 0


def _cmd_rubric(args: argparse.Namespace) -> int:
    from altitude.core.rubric import default_rubrics

    rs = default_rubrics()
    if args.ref:
        print(json.dumps(rs.get(args.ref), indent=2, default=str))
    else:
        print(rs.version)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="altitude", description="Evidence-first Snowflake partner platform")
    sub = parser.add_subparsers(dest="command", required=True)

    k = sub.add_parser("knowledge", help="knowledge-as-data tools")
    ksub = k.add_subparsers(dest="knowledge_cmd", required=True)
    ksub.add_parser("validate", help="validate every knowledge YAML file").set_defaults(func=_cmd_validate)

    g = sub.add_parser("generate", help="regenerate header-stamped artifacts under generated/")
    g.add_argument("--check", action="store_true", help="fail if regeneration would produce a diff")
    g.set_defaults(func=_cmd_generate)

    r = sub.add_parser("rubric", help="show the rubric version or resolve a reference")
    r.add_argument("ref", nargs="?")
    r.set_defaults(func=_cmd_rubric)

    for name in MODULE_CLIS:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name and name.startswith(e.name):
                continue
            raise
        mod.register(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
