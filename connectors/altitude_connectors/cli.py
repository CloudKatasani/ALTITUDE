"""``altitude connectors`` — permission manifests, read-only checks and harvests."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from datetime import datetime


def _cmd_manifest(args: argparse.Namespace) -> int:
    from .generate import grant_script
    from .manifest import available_sources, load_manifest

    if args.source is None:
        print("\n".join(available_sources()))
        return 0
    m = load_manifest(args.source)
    if args.format == "grants":
        print(grant_script(m), end="")
    else:
        print(json.dumps(m.doc, indent=2))
    return 0


def _cmd_check_sql(args: argparse.Namespace) -> int:
    from altitude.core.errors import ReadOnlyViolation

    from .manifest import load_manifest
    from .readonly import classify_statement

    scope = load_manifest(args.source).scope if args.source else None
    dialect = args.dialect or (load_manifest(args.source).dialect if args.source else "tsql")
    try:
        v = classify_statement(args.sql, dialect, scope)
    except ReadOnlyViolation as e:
        print(json.dumps({"verdict": "refused", "reason": str(e)}))
        return 2
    print(json.dumps({"verdict": "allowed", "kind": v.kind, "objects": v.objects, "parser": v.parser}))
    return 0


def _connect(args: argparse.Namespace):
    if args.duckdb:
        import duckdb

        con = duckdb.connect(args.duckdb, read_only=True)
        for spec in args.attach or []:
            name, _, path = spec.partition("=")
            con.execute(f"ATTACH '{path}' AS {name} (READ_ONLY)")
        return con, "duckdb"
    if args.driver:
        mod = importlib.import_module(args.driver)
        return mod.connect(args.dsn), None
    raise SystemExit("one of --duckdb or --driver/--dsn is required")


def _cmd_harvest(args: argparse.Namespace) -> int:
    from .agent import ExtractionAgent

    con, execute_dialect = _connect(args)
    agent = ExtractionAgent(args.source, con, engagement_id=args.engagement, system_name=args.system,
                            script_dirs=args.scripts or [], execute_dialect=execute_dialect,
                            as_of=datetime.fromisoformat(args.as_of) if args.as_of else None)
    bundle = agent.harvest()
    store = None
    if args.store:
        from altitude.core.store import Store

        store = Store(args.store)
    snap = agent.ship(snapshot_dir=args.out, store=store, snapshot_id=args.snapshot_id)
    print(json.dumps({"snapshot_id": snap.snapshot_id if snap else None, "path": str(snap.path) if snap else None,
                      "counts": bundle.counts(), "statements": bundle.meta["statements"]}, indent=2))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("connectors", help="read-only source connectors and the extraction agent")
    s = p.add_subparsers(dest="connectors_cmd", required=True)

    m = s.add_parser("manifest", help="show a published permission manifest (or list sources)")
    m.add_argument("source", nargs="?")
    m.add_argument("--format", choices=["json", "grants"], default="json")
    m.set_defaults(func=_cmd_manifest)

    c = s.add_parser("check-sql", help="vet a statement with the read-only guard")
    c.add_argument("sql")
    c.add_argument("--source", help="also enforce the source manifest's objects_read scope")
    c.add_argument("--dialect")
    c.set_defaults(func=_cmd_check_sql)

    h = s.add_parser("harvest", help="harvest a source read-only and seal a harvest snapshot")
    h.add_argument("--source", required=True, choices=["sqlserver", "oracle", "teradata"])
    h.add_argument("--engagement", required=True)
    h.add_argument("--system", required=True, help="source system name (e.g. database name)")
    h.add_argument("--duckdb", help="emulated/exported catalog in a DuckDB file (opened read-only)")
    h.add_argument("--attach", action="append", help="NAME=PATH extra DuckDB catalogs (e.g. msdb, SSISDB)")
    h.add_argument("--driver", help="DB-API module for a live source (e.g. pyodbc, oracledb, teradatasql)")
    h.add_argument("--dsn", help="connection string passed to <driver>.connect()")
    h.add_argument("--scripts", action="append", help="repository directory with BTEQ/DTSX files")
    h.add_argument("--out", required=True, help="snapshot directory")
    h.add_argument("--snapshot-id")
    h.add_argument("--as-of")
    h.add_argument("--store", help="control-plane DuckDB store to load the canonical rows into")
    h.set_defaults(func=_cmd_harvest)


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(prog="altitude")
    register(parser.add_subparsers(dest="command", required=True))
    a = parser.parse_args()
    sys.exit(a.func(a))
