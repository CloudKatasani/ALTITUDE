"""``altitude diag`` — run, export, bootstrap, harvest and track Package D diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _store(path: str | None):
    if not path:
        return None
    from altitude.core.store import Store

    from . import lifecycle  # noqa: F401 - registers append-only tables

    return Store(path)


def _run(args: argparse.Namespace):
    from altitude.core.snapshot import Snapshot

    from .engine import DiagnosticsEngine

    snap = Snapshot.open(args.snapshot, verify=True)
    return snap, DiagnosticsEngine().run(snap, tier=args.tier)


def _cmd_run(args: argparse.Namespace) -> int:
    from . import lifecycle
    from .exports import suggestions_json

    snap, result = _run(args)
    store = _store(args.store)
    run_id = lifecycle.persist(result, store, snapshot=snap, tenant_id=args.tenant) if store else None
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "suggestions.json").write_text(suggestions_json(result, lifecycle.overlay_status(result, store)))
    summary = {
        **result.stamp,
        "run_id": run_id,
        "platform_health_index": result.scorecard["platform_health_index"],
        "suggestions": len(result.suggestions),
        "in_review_queue": sum(1 for d in result.details if d.needs_review),
        "value_p50_usd": sum((s["value"]["annualised_usd"] or {}).get("p50", 0) for s in result.suggestions),
        "domains": {d["id"]: d["score"] for d in result.scorecard["domains"]},
        "next_packages": [r["package"] for r in result.recommendations],
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _cmd_export(args: argparse.Namespace) -> int:
    from . import lifecycle
    from .exports import ALL_FORMATS, export_all

    _, result = _run(args)
    store = _store(args.store)
    formats = None if not args.formats else (ALL_FORMATS if args.formats == ["all"] else args.formats)
    written = export_all(result, args.out, formats=formats, recs=lifecycle.overlay_status(result, store), theme=args.theme)
    print(json.dumps({k: str(v) for k, v in sorted(written.items())}, indent=2))
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    from .bootstrap import BootstrapConfig, bootstrap_sql, kill_test, permission_manifest, teardown_sql

    cfg = BootstrapConfig(credit_budget=args.credit_budget, monitor_admin_role=args.monitor_admin_role,
                          **({"public_key": args.public_key} if args.public_key else {}))
    problems = kill_test(cfg=cfg)
    if problems:
        for p in problems:
            print(f"kill-test: {p}", file=sys.stderr)
        return 1
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "bootstrap.sql").write_text(bootstrap_sql(cfg))
        (out / "teardown.sql").write_text(teardown_sql(cfg))
        (out / "permission_manifest.json").write_text(json.dumps(permission_manifest(cfg), indent=2, sort_keys=True) + "\n")
        print(f"wrote {out}/bootstrap.sql, teardown.sql, permission_manifest.json (kill-test: OK)")
    else:
        print(teardown_sql(cfg) if args.teardown else bootstrap_sql(cfg), end="")
    return 0


def _cmd_status(args: argparse.Namespace) -> int:
    from altitude.core.errors import ApprovalRequired

    from . import lifecycle

    store = _store(args.store)
    if args.suggestion:
        try:
            if args.review:
                lifecycle.review(store, args.suggestion, args.reviewer, args.review, args.comment)
            if args.set_status:
                lifecycle.transition(store, args.suggestion, args.set_status, actor=args.actor or args.reviewer or "",
                                     reviewer=args.reviewer, comment=args.comment)
        except (ApprovalRequired, lifecycle.LifecycleError, KeyError) as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        row = lifecycle.get(store, args.suggestion)
        print(json.dumps({"suggestion_id": row["suggestion_id"], "status": row["status"], "reviewer": row["reviewer"],
                          "in_review_queue": lifecycle.in_review_queue(store, args.suggestion),
                          "history": [{k: str(v) for k, v in h.items()} for h in lifecycle.history(store, args.suggestion)]},
                         indent=2))
        return 0
    rows = lifecycle.statuses(store, args.snapshot_id)
    for r in rows:
        flag = "REVIEW" if lifecycle.in_review_queue(store, r["suggestion_id"]) else ""
        print(f"{r['priority_rank']:>3} {r['suggestion_id']} {r['check_id']:<11} {r['status']:<14} "
              f"{float(r['confidence']):.2f} {flag:<6} {r['title']}")
    print(f"{len(rows)} suggestion(s)")
    return 0


def _cmd_harvest(args: argparse.Namespace) -> int:  # pragma: no cover - needs a live account
    from .harvest import LiveHarvester, connect_snowflake

    params = json.loads(Path(args.connection).read_text())
    inputs = json.loads(Path(args.client_inputs).read_text()) if args.client_inputs else {}
    con = connect_snowflake(**params)
    snap = LiveHarvester(con, window_days=args.days, client_inputs=inputs).harvest(args.out)
    print(json.dumps({"snapshot_id": snap.snapshot_id, "path": str(snap.path), "content_hash": snap.content_hash}, indent=2))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("diag", help="Package D: platform deep diagnostics")
    s = p.add_subparsers(dest="diag_cmd", required=True)

    def snapshot_args(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--snapshot", required=True, help="path to a sealed diagnostic snapshot (.duckdb)")
        sp.add_argument("--tier", default="D2", choices=["D0", "D1", "D2", "D3"])
        sp.add_argument("--store", help="control-plane store (DuckDB file) for lifecycle state")

    r = s.add_parser("run", help="run the suggestion engine on a sealed snapshot")
    snapshot_args(r)
    r.add_argument("--out", help="directory for suggestions.json")
    r.add_argument("--tenant")
    r.set_defaults(func=_cmd_run)

    e = s.add_parser("export", help="generate every deliverable from one sealed snapshot")
    snapshot_args(e)
    e.add_argument("--out", required=True)
    e.add_argument("--formats", nargs="*", help="subset of formats, or 'all' (default: the tier's deliverables)")
    e.add_argument("--theme", help="white-label theme (knowledge/theme/<name>.yaml)")
    e.set_defaults(func=_cmd_export)

    b = s.add_parser("bootstrap", help="least-privilege access bootstrap / teardown / permission manifest")
    b.add_argument("--out", help="write bootstrap.sql, teardown.sql and permission_manifest.json here")
    b.add_argument("--teardown", action="store_true", help="print the teardown script instead")
    b.add_argument("--credit-budget", type=float, default=None, help="override rubric.diagnostics.access.credit_budget")
    b.add_argument("--monitor-admin-role", default="SYSADMIN")
    b.add_argument("--public-key", help="RSA public key for the service user")
    b.set_defaults(func=_cmd_bootstrap)

    st = s.add_parser("status", help="list suggestion lifecycle state, or review / transition one suggestion")
    st.add_argument("--store", required=True)
    st.add_argument("--snapshot-id")
    st.add_argument("--suggestion")
    st.add_argument("--review", choices=["approved", "rejected", "modified"])
    st.add_argument("--set-status", choices=["accepted", "implemented", "value_realised", "rejected"])
    st.add_argument("--reviewer")
    st.add_argument("--actor")
    st.add_argument("--comment")
    st.set_defaults(func=_cmd_status)

    h = s.add_parser("harvest", help="live read-only harvest (requires the optional snowflake extra)")
    h.add_argument("--connection", required=True, help="JSON file with snowflake.connector.connect() arguments")
    h.add_argument("--client-inputs", help="JSON file with engagement intake (contract price, commitments, tiers, SLAs)")
    h.add_argument("--days", type=int, default=90)
    h.add_argument("--out", required=True)
    h.set_defaults(func=_cmd_harvest)
