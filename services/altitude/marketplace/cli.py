"""``altitude marketplace`` — certify data products and agents on a snapshot; emit publishable SQL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _assess(args: argparse.Namespace) -> dict:
    from altitude.core.snapshot import Snapshot

    from .trust import assess

    return assess(Snapshot.open(args.snapshot), package_o=args.package_o)


def _cmd_assess(args: argparse.Namespace) -> int:
    r = _assess(args)
    if args.json:
        print(json.dumps(r, indent=2, default=str))
        return 0
    for p in r["products"]:
        print(f"{p['id']:<20} {p['status']:<10} score {p['score']:.2f}  consumers {p['consumers']:<3} "
              + ("; ".join(c["detail"] for c in p["checks"] if not c["passed"]) or "all checks pass"))
    for a in r["agents"]:
        print(f"{a['id']:<20} {a['status']:<10} " + ("; ".join(c["detail"] for c in a["checks"] if not c["passed"])
                                                     or "ready to publish"))
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    from altitude.core.generated import stamp

    from .catalog import agents, products
    from .render import agent_sql, product_sql

    r = _assess(args)
    ok_p = {p["id"] for p in r["products"] if p["certified"]}
    ok_a = {a["id"] for a in r["agents"] if a["ready"]}
    by_id = {p["id"]: p for p in products()}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    parts = [product_sql(p) for p in products() if p["id"] in ok_p]
    parts += [agent_sql(a, by_id) for a in agents() if a["id"] in ok_a]
    src = f"marketplace certification on {r['snapshot_id']} ({r['assessment_hash']})"
    (out / "publish.sql").write_text(stamp("\n".join(parts), ".sql", src))
    (out / "certification.json").write_text(json.dumps(r, indent=2, default=str) + "\n")
    print(f"publishable: {len(ok_p)} product(s), {len(ok_a)} agent(s) -> {out / 'publish.sql'}; "
          f"held back: {sorted(set(by_id) - ok_p) + sorted({a['id'] for a in agents()} - ok_a)}")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("marketplace", help="data product & agent marketplace: certify and publish")
    s = p.add_subparsers(dest="marketplace_cmd", required=True)
    for name, func, help_text in (("assess", _cmd_assess, "certify products and agents on a sealed snapshot"),
                                  ("publish", _cmd_publish, "write listing/agent SQL for certified items only")):
        c = s.add_parser(name, help=help_text)
        c.add_argument("--snapshot", required=True)
        c.add_argument("--package-o", action="store_true", help="Package O semantic layer is deployed")
        if name == "assess":
            c.add_argument("--json", action="store_true")
        else:
            c.add_argument("--out", default="out/marketplace")
        c.set_defaults(func=func)
