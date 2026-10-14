"""``altitude validation`` — tiered reconciliation (M6).

    altitude validation levels [--tier tier1]
    altitude validation suite --config tables.yaml
    altitude validation run --config tables.yaml --source src.duckdb --target tgt.duckdb --db store.duckdb
                            --mismatch-dir ./mismatch [--label run-1] [--as-of 2026-10-14] [--timings t.json]
    altitude validation assign-owner --db store.duckdb --object SALES.ORDERS --owner jane@client --by lead@partner
    altitude validation accept --db store.duckdb --run RUN --cluster CLUSTER --approver jane@client
                               --review-by 2027-01-31 --description "..."
    altitude validation summary --db store.duckdb [--engagement ENG] [--as-of DATE] [--format md|json]
    altitude validation demo --out DIR [--case TD-01 ...]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml


def _as_of(args) -> date:
    return date.fromisoformat(args.as_of) if getattr(args, "as_of", None) else date.today()


def _specs(path: str):
    from .suite import TableSpec

    doc = yaml.safe_load(Path(path).read_text()) or {}
    return [TableSpec.from_dict(t) for t in doc.get("tables", [])]


def _cmd_levels(args) -> int:
    from .config import LEVELS, default_knowledge

    k = default_knowledge()
    tiers = [args.tier] if args.tier else list(k.tiers)
    for t in tiers:
        tier = k.tier(t)
        print(f"{t}: " + ", ".join(f"{lv}={tier['levels'][lv]}" for lv in LEVELS) + f"  ({tier['threshold_ref']})")
    return 0


def _cmd_suite(args) -> int:
    from .suite import generate_suite

    out = []
    for spec in _specs(args.config):
        s = generate_suite(spec)
        out.append({"suite_id": s.suite_id, "object_id": spec.object_id, "tier": s.tier,
                    "normalisation_rule_version": s.normaliser.version,
                    "checks": [{"check_id": c.check_id, "level": c.level, "mode": c.mode, **c.definition}
                               for c in s.checks]})
    print(json.dumps(out, indent=2))
    return 0


def _cmd_run(args) -> int:
    import duckdb

    from altitude.core.store import Store

    from .deviation import assign_data_owner, data_owner
    from .endpoint import Endpoint
    from .engine import ValidationEngine
    from .suite import generate_suite

    store = Store(args.db)
    src = Endpoint(duckdb.connect(args.source, read_only=True), "duckdb", "source")
    tgt = Endpoint(duckdb.connect(args.target, read_only=True), "duckdb", "target")
    timings = json.loads(Path(args.timings).read_text()) if args.timings else None
    engine = ValidationEngine(store, src, tgt, args.mismatch_dir)
    worst = 0
    for spec in _specs(args.config):
        if spec.data_owner and not data_owner(store, spec.object_id):
            assign_data_owner(store, spec.object_id, spec.data_owner, args.actor)
        res = engine.run(generate_suite(spec), run_label=args.label, as_of=_as_of(args),
                         timings=(timings or {}).get(spec.object_id), actor=args.actor)
        print(f"{spec.object_id} [{spec.tier}] {res.status}")
        for lv, r in res.levels.items():
            print(f"  {lv} {r.result:<18} run={r.run_id}" + (f" keys={r.mismatch_key_ref}" if r.mismatch_key_ref else ""))
            for c in r.clusters:
                print(f"     cluster {c.cluster_id} {c.signature_key} n={c.count} -> "
                      f"{c.known_issue_id or 'unmapped'} ({c.confidence:.2f})")
        worst = max(worst, 1 if res.status == "fail" else 0)
    return worst


def _cmd_assign(args) -> int:
    from altitude.core.store import Store

    from .deviation import assign_data_owner

    assign_data_owner(Store(args.db), args.object, args.owner, args.by)
    print(f"{args.object}: data owner {args.owner}")
    return 0


def _cmd_accept(args) -> int:
    from altitude.core.store import Store

    from .deviation import accept_deviation

    dev = accept_deviation(Store(args.db), args.run, args.cluster, args.approver,
                           date.fromisoformat(args.review_by), args.description, as_of=_as_of(args))
    print(dev)
    return 0


def _cmd_summary(args) -> int:
    from altitude.core.store import Store

    from .summary import render_md, tier_summary

    summ = tier_summary(Store(args.db), _as_of(args), args.engagement)
    sys.stdout.write(json.dumps(summ, indent=2) + "\n" if args.format == "json" else render_md(summ))
    return 0


def _cmd_demo(args) -> int:
    from altitude.core.store import Store

    from .deviation import assign_data_owner
    from .engine import ValidationEngine
    from .suite import generate_suite
    from .summary import render_md, tier_summary
    from .synthetic import CASES

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    store = Store(out / "control_plane.duckdb")
    for name in args.case or list(CASES):
        case = CASES[name]()
        try:
            assign_data_owner(store, case.spec.object_id, case.spec.data_owner, "demo")
            res = ValidationEngine(store, case.source, case.target, out / "mismatch").run(
                generate_suite(case.spec), run_label=f"demo-{name}", as_of=_as_of(args))
            found = sorted({c.known_issue_id for c in res.clusters if c.known_issue_id})
            print(f"{name:<6} {res.status:<18} clusters -> {', '.join(found) or '-'}")
        finally:
            case.close()
    sys.stdout.write("\n" + render_md(tier_summary(store, _as_of(args))))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("validation", help="tiered L0-L5 validation, mismatch triage and deviations (M6)")
    s = p.add_subparsers(dest="validation_cmd", required=True)

    lv = s.add_parser("levels", help="show validation levels per tier")
    lv.add_argument("--tier")
    lv.set_defaults(func=_cmd_levels)

    su = s.add_parser("suite", help="generate L0-L5 suites for the tables in a config file")
    su.add_argument("--config", required=True)
    su.set_defaults(func=_cmd_suite)

    r = s.add_parser("run", help="run suites in-boundary against source and target databases")
    r.add_argument("--config", required=True)
    r.add_argument("--source", required=True, help="source DuckDB file (emulated source / extract)")
    r.add_argument("--target", required=True, help="target DuckDB file (Snowflake stand-in)")
    r.add_argument("--db", required=True, help="control-plane store (DuckDB file)")
    r.add_argument("--mismatch-dir", required=True, help="in-boundary directory for mismatch key files")
    r.add_argument("--label", default="run-1")
    r.add_argument("--as-of")
    r.add_argument("--timings", help="JSON {object_id: [L5 timing dicts]}")
    r.add_argument("--actor", default="validation-engine")
    r.set_defaults(func=_cmd_run)

    a = s.add_parser("assign-owner", help="register the data owner who may accept deviations")
    a.add_argument("--db", required=True)
    a.add_argument("--object", required=True)
    a.add_argument("--owner", required=True)
    a.add_argument("--by", required=True)
    a.set_defaults(func=_cmd_assign)

    ac = s.add_parser("accept", help="data owner accepts a mismatch cluster as a deviation")
    ac.add_argument("--db", required=True)
    ac.add_argument("--run", required=True)
    ac.add_argument("--cluster", required=True)
    ac.add_argument("--approver", required=True)
    ac.add_argument("--review-by", required=True)
    ac.add_argument("--description", required=True)
    ac.add_argument("--as-of")
    ac.set_defaults(func=_cmd_accept)

    sm = s.add_parser("summary", help="tier-level reconciliation summary for the go/no-go pack")
    sm.add_argument("--db", required=True)
    sm.add_argument("--engagement")
    sm.add_argument("--as-of")
    sm.add_argument("--format", choices=["md", "json"], default="md")
    sm.set_defaults(func=_cmd_summary)

    d = s.add_parser("demo", help="run the synthetic drift cases end to end")
    d.add_argument("--out", required=True)
    d.add_argument("--case", action="append", help="drift case (repeatable); default all")
    d.add_argument("--as-of")
    d.set_defaults(func=_cmd_demo)
