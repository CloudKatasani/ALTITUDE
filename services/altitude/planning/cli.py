"""``altitude plan`` — waves, estimates, pattern recommendations, gates and factory transitions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _json_arg(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    p = Path(value)
    return json.loads(p.read_text() if p.exists() else value)


def _store(path: str | None):
    if not path:
        return None
    from altitude.core.store import Store

    return Store(path)


def _ctx(args: argparse.Namespace, store: Any = None):
    from .context import PlanningContext

    return PlanningContext.load(args.assessment, args.harvest, store=store, inputs=_json_arg(args.inputs))


def _cmd_waves(args: argparse.Namespace) -> int:
    from .waves import WavePlanner, record_plan

    store = _store(args.store)
    ctx = _ctx(args, store)
    plan = WavePlanner(ctx, store=store).plan()
    if store is not None:
        record_plan(store, plan, ctx)
    payload = json.dumps(plan.to_dict(), indent=2, default=str)
    if args.out:
        Path(args.out).write_text(payload + "\n")
    summary = {"plan_id": plan.plan_id, "status": plan.status, "rubric_version": plan.rubric_version,
               "waves": [{"wave": w.ordinal, "name": w.name, "objects": len(w.object_ids), "weeks": w.weeks,
                          "start": str(w.start_date), "cutover": str(w.cutover_date), "pattern": w.pattern}
                         for w in plan.waves],
               "violations": plan.violations, "p50_hours": plan.programme_estimate["p50_hours"],
               "p80_hours": plan.programme_estimate["p80_hours"]}
    print(json.dumps(summary, indent=2, default=str))
    return 0 if not [v for v in plan.violations if v["rule"] != "requires_gate"] else 3


def _cmd_estimate(args: argparse.Namespace) -> int:
    from .estimation import Estimator, record_estimate

    store = _store(args.store)
    est = Estimator(_ctx(args, store)).estimate("programme", None, include_foundation=True, include_retired=True,
                                                cutovers=args.cutovers)
    if store is not None:
        record_estimate(store, est)
    print(json.dumps(est.to_dict(), indent=2, default=str))
    return 0


def _cmd_recommend(args: argparse.Namespace) -> int:
    from .recommender import evidence_inputs, recommend

    ctx = _ctx(args)
    inputs = {**ctx.inputs, **evidence_inputs(ctx, ctx.in_scope())}
    print(json.dumps(recommend(inputs, scope="programme", snapshot_id=ctx.snapshot_id).to_dict(), indent=2))
    return 0


def _cmd_gate(args: argparse.Namespace) -> int:
    from altitude.assessment.engine import load_assessment

    from .gates import collect_metrics, evaluate_gate, record_gate

    store = _store(args.store)
    result = load_assessment(args.assessment)
    metrics = collect_metrics(assessment=result, store=store, facts=_json_arg(args.facts))
    d = evaluate_gate(args.gate, metrics, snapshot_id=result.snapshot_id,
                      engagement_id=result.summary.get("engagement_id") or args.engagement or "")
    if store is not None:
        record_gate(store, d)
    print(json.dumps(d.to_dict(), indent=2, default=str))
    return 0 if d.passed else 4


def _cmd_transition(args: argparse.Namespace) -> int:
    from .factory import Factory

    rec = Factory(_store(args.store)).transition(args.wave, args.object, args.to, actor=args.actor,
                                                 actor_type=args.actor_type, evidence_ref=args.evidence,
                                                 confidence=args.confidence, note=args.note)
    print(json.dumps(rec, indent=2, default=str))
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("plan", help="planning & estimation: waves, estimates, patterns, gates, factory")
    s = p.add_subparsers(dest="plan_cmd", required=True)

    def inputs(x: argparse.ArgumentParser) -> None:
        x.add_argument("--assessment", required=True, help="assessment snapshot .duckdb")
        x.add_argument("--harvest", help="harvest snapshot .duckdb (or registered in --store)")
        x.add_argument("--inputs", help="programme inputs JSON (file or literal): deadline_weeks, start_date, ...")
        x.add_argument("--store")

    w = s.add_parser("waves", help="plan waves under the wave rules stored as data")
    inputs(w)
    w.add_argument("--out", help="write the full plan JSON here")
    w.set_defaults(func=_cmd_waves)

    e = s.add_parser("estimate", help="programme estimate (p50/p80, confidence, rationale)")
    inputs(e)
    e.add_argument("--cutovers", type=int, default=1)
    e.set_defaults(func=_cmd_estimate)

    r = s.add_parser("recommend", help="programme-level pattern recommendation with dissent")
    inputs(r)
    r.set_defaults(func=_cmd_recommend)

    g = s.add_parser("gate", help="evaluate and record a readiness gate against an assessment snapshot")
    g.add_argument("gate")
    g.add_argument("--assessment", required=True)
    g.add_argument("--facts", help="attested facts JSON, e.g. {\"business_case_approved\": true}")
    g.add_argument("--engagement")
    g.add_argument("--store")
    g.set_defaults(func=_cmd_gate)

    t = s.add_parser("transition", help="record a factory state transition")
    t.add_argument("--store", required=True)
    t.add_argument("--wave", required=True)
    t.add_argument("--object", required=True)
    t.add_argument("--to", required=True)
    t.add_argument("--actor", required=True)
    t.add_argument("--actor-type", default="human", choices=["human", "agent", "system"])
    t.add_argument("--evidence", required=True)
    t.add_argument("--confidence", type=float, required=True)
    t.add_argument("--note")
    t.set_defaults(func=_cmd_transition)
