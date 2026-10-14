"""``altitude obs`` — Package O: harvest, KPIs, reconciliation, alerts, dashboards, ask-the-platform, value loop."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


def _db(args: argparse.Namespace):
    from .db import ObsDatabase

    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    return ObsDatabase(args.db)


def _date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def _print(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def _cmd_harvest(args: argparse.Namespace) -> int:
    from .harvest import harvest_registry

    db = _db(args)
    results = harvest_registry(db, args.registry, _date(args.as_of) or date.today(), days=args.days,
                               native_retention_days=args.retention_days)
    _print([r.summary() for r in results])
    return 0 if all(r.ok for r in results) else 1


def _cmd_kpis(args: argparse.Namespace) -> int:
    from .kpi import compute_kpis

    counts = compute_kpis(_db(args))
    _print({"kpis": len(counts), "rows": counts})
    return 0


def _cmd_reconcile(args: argparse.Namespace) -> int:
    from .reconcile import reconcile

    r = reconcile(_db(args))
    _print({"ok": r["ok"], "tolerance_pct": r["tolerance_pct"], "months": r["months"],
            "days_failed": r["days_failed"][:20]})
    return 0 if r["ok"] else 1


def _cmd_alerts(args: argparse.Namespace) -> int:
    from .alerts import evaluate_alerts
    from .config import load_registry
    from .routing import routing_test, routing_test_due

    db = _db(args)
    reg = load_registry(args.registry)
    day = _date(args.date) or db.scalar("SELECT max(PERIOD) FROM KPI.KPI_COST_011")
    events = evaluate_alerts(db, reg, day, args.outbox)
    out = {"evaluated_for": day, "events": [{k: e[k] for k in ("ALERT_ID", "ACCOUNT_NAME", "DIMENSION", "SEVERITY",
                                                               "ROUTE", "CHANNEL", "RUNBOOK", "STATUS", "MESSAGE")}
                                            for e in events]}
    if args.routing_test or routing_test_due(db, day):
        out["routing_test"] = routing_test(db, reg, args.outbox, day)
    _print(out)
    return 0


def _cmd_dashboards(args: argparse.Namespace) -> int:
    from .dashboards import render_dashboards

    value = json.loads(Path(args.value_summary).read_text()) if args.value_summary else None
    if isinstance(value, dict) and "qbr" in value:  # output of `altitude obs value --out`
        value = value["qbr"]
    paths = render_dashboards(_db(args), args.out, as_of=_date(args.as_of), account=args.account, theme=args.theme,
                              registry=args.registry, value_summary=value)
    _print(paths)
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    from .agent import AskThePlatform

    store = None
    if args.store:
        from altitude.core.store import Store

        store = Store(args.store)
    ans = AskThePlatform(_db(args), store=store).ask(args.question, account=args.account)
    if args.json:
        _print(ans.to_dict())
    else:
        print(ans.text)
        for c in ans.citations:
            print(f"  cites {c['kpi_id']} ({c['kpi_table']}, {c['rows_total']} rows; sources: "
                  + ", ".join(f"{s['table']}={s['rows_in_window']}" for s in c["source_tables"]) + ")")
        print(f"  confidence {ans.confidence:.2f} — {ans.rationale}")
    return 0 if ans.answered else 2


def _cmd_value(args: argparse.Namespace) -> int:
    from altitude.core.store import Store

    from .value import measure_suggestions, qbr_summary

    db = _db(args)
    suggestions = json.loads(Path(args.suggestions).read_text())
    store = Store(args.store) if args.store else Store()
    measured = measure_suggestions(db, suggestions, store=store, account=args.account, tenant_id=args.tenant)
    qbr = qbr_summary(db, measured, account=args.account, baseline_health_index=args.baseline_health_index,
                      store=store, tenant_id=args.tenant)
    result = {"suggestions": measured, "qbr": qbr}
    if args.out:
        Path(args.out).write_text(json.dumps(result, indent=2, default=str) + "\n")
    _print(qbr)
    return 0


def _cmd_freshness(args: argparse.Namespace) -> int:
    from .harvest import freshness

    rows = freshness(_db(args), _date(args.as_of) or date.today())
    _print({"late": [r for r in rows if not r["met"]], "sources": len(rows)})
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("obs", help="Package O — platform observability")
    s = p.add_subparsers(dest="obs_cmd", required=True)

    def add(name: str, func, help_text: str) -> argparse.ArgumentParser:
        sp = s.add_parser(name, help=help_text)
        sp.add_argument("--db", default=".altitude/obs.duckdb", help="OBS database (DuckDB file)")
        sp.set_defaults(func=func)
        return sp

    h = add("harvest", _cmd_harvest, "harvest every account in a tenant registry into RAW")
    h.add_argument("--registry", help="tenant accounts registry YAML (default: example tenant)")
    h.add_argument("--as-of", help="harvest as of this date (YYYY-MM-DD)")
    h.add_argument("--days", type=int, help="synthetic accounts: days of history the source holds")
    h.add_argument("--retention-days", type=int, help="override the sources' native retention window")

    add("kpis", _cmd_kpis, "build CURATED, KPI tables, Health Index and SEMANTIC")
    add("reconcile", _cmd_reconcile, "reconcile cost KPIs to METERING_DAILY_HISTORY credits billed")

    a = add("alerts", _cmd_alerts, "evaluate the alert catalogue and route to the outbox")
    a.add_argument("--date", help="evaluate for this day (default: latest KPI day)")
    a.add_argument("--registry")
    a.add_argument("--outbox", default=".altitude/outbox")
    a.add_argument("--routing-test", action="store_true", help="also run the routing test now")

    d = add("dashboards", _cmd_dashboards, "render dashboards 1, 2, 4 and chargeback statements (HTML)")
    d.add_argument("--out", required=True)
    d.add_argument("--as-of")
    d.add_argument("--account")
    d.add_argument("--theme")
    d.add_argument("--registry")
    d.add_argument("--value-summary", help="QBR JSON from `altitude obs value` to show on dashboard 1")

    q = add("ask", _cmd_ask, "ask the platform a question (answers from certified KPIs, with citations)")
    q.add_argument("question")
    q.add_argument("--account")
    q.add_argument("--json", action="store_true")
    q.add_argument("--store", help="control-plane store (records the inference / review queue)")

    v = add("value", _cmd_value, "suggestion-to-value: measure implemented Package D suggestions; QBR summary")
    v.add_argument("--suggestions", required=True, help="JSON list of suggestion records")
    v.add_argument("--store", help="control-plane store (DuckDB) to record measurements and transitions")
    v.add_argument("--account")
    v.add_argument("--tenant")
    v.add_argument("--baseline-health-index", type=float, help="Package D baseline Health Index")
    v.add_argument("--out", help="write measured suggestions + QBR JSON here")

    f = add("freshness", _cmd_freshness, "harvest freshness per source vs rubric SLAs")
    f.add_argument("--as-of")


if __name__ == "__main__":  # pragma: no cover
    parser = argparse.ArgumentParser(prog="altitude-obs")
    register(parser.add_subparsers(dest="command", required=True))
    a = parser.parse_args()
    sys.exit(int(a.func(a) or 0))
