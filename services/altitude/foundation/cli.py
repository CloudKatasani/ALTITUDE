"""``altitude foundation ...`` — landing-zone Terraform and the Well-Architected checker."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_validate(args: argparse.Namespace) -> int:
    from . import landing_zone, tflint
    from .generate import terraform_files

    lz = landing_zone.load(strict=False)
    problems = landing_zone.validate(lz)
    problems += tflint.lint(terraform_files(), database_regex=lz["naming"]["database_regex"])
    for p in problems:
        print(p, file=sys.stderr)
    print(f"landing zone {lz['id']}: {len(lz.databases)} databases, {len(lz.access_roles)} access roles, "
          f"{len(lz['functional_roles'])} functional roles, {len(lz.warehouses)} warehouses — "
          f"{'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def cmd_terraform(args: argparse.Namespace) -> int:
    from . import tflint

    if args.lint:
        files = {p.name: p.read_text() for p in sorted(Path(args.lint).glob("*.tf"))}
        problems = tflint.lint(files, database_regex=args.database_regex)
        for p in problems:
            print(p, file=sys.stderr)
        print(f"terraform lint: {'OK' if not problems else f'{len(problems)} problem(s)'} ({len(files)} files)")
        return 1 if problems else 0
    from .generate import terraform_files

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, body in terraform_files().items():
        (out / name).write_text(body)
        print(f"wrote {out / name}")
    return 0


def cmd_wa_check(args: argparse.Namespace) -> int:
    from altitude.core.snapshot import Snapshot

    from . import wa

    snap = Snapshot.open(args.snapshot, verify=True)
    report = wa.run(snap)
    if args.store:
        from altitude.core.store import Store

        wa.persist(Store(args.store), report)
    if args.markdown:
        Path(args.markdown).write_text(wa.to_markdown(report))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"{report.snapshot_id}: overall {report.overall} ({report.rating}); {len(report.findings)} finding(s); "
              f"report {report.report_hash}")
        for f in report.findings:
            print(f"  {f.check_id:<12} {f.severity:<8} {f.title} -> {f.playbook['id']} [{', '.join(f.objects[:5])}]")
    return 0


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("foundation", help="Snowflake Foundation: landing-zone Terraform, Well-Architected checks")
    sub = p.add_subparsers(dest="foundation_cmd", required=True)
    sub.add_parser("validate", help="validate the landing-zone model and its generated Terraform").set_defaults(
        func=cmd_validate)
    t = sub.add_parser("terraform", help="render the landing zone to Terraform, or lint a Terraform directory")
    t.add_argument("--out", default="out/terraform")
    t.add_argument("--lint", help="directory of .tf files to lint instead of rendering")
    t.add_argument("--database-regex", default=None)
    t.set_defaults(func=cmd_terraform)
    w = sub.add_parser("wa-check", help="run the Well-Architected checks on a sealed snapshot")
    w.add_argument("--snapshot", required=True)
    w.add_argument("--json", action="store_true")
    w.add_argument("--markdown", help="write a markdown report to this path")
    w.add_argument("--store", help="persist findings to this control-plane store")
    w.set_defaults(func=cmd_wa_check)
