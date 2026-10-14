"""``altitude synthetic`` — build synthetic snapshots for demos and tests."""

from __future__ import annotations

import argparse
import json
from datetime import date


def _cmd_snapshot(args: argparse.Namespace) -> int:
    from .snowflake_account import AccountSpec, build_snapshot

    spec = AccountSpec(account_name=args.account, organization=args.org, profile=args.profile, days=args.days,
                       end_date=date.fromisoformat(args.end_date), seed=args.seed)
    snap, account = build_snapshot(args.out, spec, snapshot_id=args.snapshot_id)
    print(json.dumps({"snapshot_id": snap.snapshot_id, "path": str(snap.path), "content_hash": snap.content_hash,
                      "seeded_issues": len(account.seeded)}, indent=2))
    if args.ground_truth:
        with open(args.ground_truth, "w") as fh:
            json.dump(account.ground_truth(), fh, indent=2)
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("synthetic", help="synthetic Snowflake estates with seeded issues")
    s = p.add_subparsers(dest="synthetic_cmd", required=True)
    snap = s.add_parser("snapshot", help="generate and seal a synthetic diagnostic snapshot")
    snap.add_argument("--out", required=True)
    snap.add_argument("--account", default="ACME_PROD")
    snap.add_argument("--org", default="ACME")
    snap.add_argument("--profile", choices=["seeded", "clean"], default="seeded")
    snap.add_argument("--days", type=int, default=90)
    snap.add_argument("--end-date", default="2026-09-30")
    snap.add_argument("--seed", type=int, default=7)
    snap.add_argument("--snapshot-id")
    snap.add_argument("--ground-truth", help="write seeded/control ground truth JSON here")
    snap.set_defaults(func=_cmd_snapshot)
