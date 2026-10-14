"""Wave planner (Sections 9.1–9.3): dependency clusters → waves, governed by rules stored as data.

``knowledge/planning/wave_rules.yaml`` lists the rules; each names an
executable rule in :data:`RULES`. The planner applies them while building the
plan and :func:`validate_plan` re-checks the finished plan against the same
data, so a plan can never silently break a rule:

- WR-01 dependency clusters (connected components of the lineage graph, not
  schema names; shared hub objects are placed by dependency order);
- WR-02 wave 1 is a thin vertical slice (source → transform → consumer);
- WR-03 every wave fits ``rubric.gates.waves.max_weeks_per_wave`` (large
  clusters are split along dependency layers, producers first);
- WR-04 regulatory / month-end objects never cut over in the last N business
  days of a quarter (the wave is shifted past quarter end);
- WR-05 each wave contains something a business user uses;
- WR-06 producers move no later than their consumers;
- WR-07 the plan is baselined only after the ``assess_exit`` gate passed on the
  same assessment snapshot.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

import yaml

from altitude.core.errors import AltitudeError
from altitude.core.ids import canonical_json, stable_id
from altitude.core.paths import knowledge_dir
from altitude.core.rubric import RubricSet, default_rubrics

from .context import PlanningContext
from .estimation import Estimate, Estimator, record_estimate
from .gates import gate_passed
from .recommender import Recommendation, evidence_inputs, recommend, record_recommendation


# --------------------------------------------------------------------------- data

SLICE = "SLICE"  # cluster label of the wave-1 vertical slice (carved across clusters by design)
DEPENDENCY_KINDS = frozenset({"reads", "writes", "calls", "schedules"})  # "from" references "to"


def load_rules(root: Path | None = None) -> dict[str, Any]:
    doc = yaml.safe_load(((root or knowledge_dir()) / "planning" / "wave_rules.yaml").read_text())
    for r in doc["rules"]:
        if r["rule"] not in RULES:
            raise AltitudeError(f"wave rule {r['id']} names unknown rule {r['rule']!r}")
    return doc


@dataclass
class Wave:
    wave_id: str
    ordinal: int
    name: str
    object_ids: list[str]
    weeks: int
    hours_p50: float
    start_date: date
    end_date: date
    cutover_date: date
    tags: list[str] = field(default_factory=list)
    consumables: list[str] = field(default_factory=list)
    clusters: list[str] = field(default_factory=list)
    hubs: list[str] = field(default_factory=list)
    thin_slice: bool = False
    freeze_shift_days: int = 0
    pattern: str = ""
    recommendation: dict[str, Any] = field(default_factory=dict)
    estimate: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class WavePlan:
    plan_id: str
    engagement_id: str | None
    snapshot_id: str
    harvest_snapshot_id: str
    rubric_version: str
    rules_version: str
    start_date: date
    waves: list[Wave]
    decommission: list[str]
    violations: list[dict[str, Any]]
    status: str
    status_reasons: list[str]
    programme_estimate: dict[str, Any]
    programme_recommendation: dict[str, Any]
    clusters: dict[str, list[str]] = field(default_factory=dict)  # label (".n" = chunk of a split cluster) → ids
    hubs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def wave_of(self) -> dict[str, int]:
        return {oid: w.ordinal for w in self.waves for oid in w.object_ids}


# --------------------------------------------------------------------------- calendar helpers


def business_days_back(end: date, n: int) -> date:
    """The n-th business day counting back from ``end`` (inclusive)."""
    d, seen = end, 0
    while True:
        if d.weekday() < 5:  # threshold-ok: Monday–Friday are business days
            seen += 1
            if seen == n:
                return d
        d -= timedelta(days=1)


def last_business_day_on_or_before(d: date) -> date:
    while d.weekday() >= 5:  # threshold-ok: weekend
        d -= timedelta(days=1)
    return d


def next_business_day_after(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:  # threshold-ok: weekend
        d += timedelta(days=1)
    return d


def quarter_end(d: date, fy_start_month: int) -> date:
    offset = (d.month - fy_start_month) % 12
    q_start_month = (d.month - offset % 3 - 1) % 12 + 1
    year = d.year if q_start_month <= d.month else d.year - 1
    q_start = date(year, q_start_month, 1)
    m = q_start.month + 3
    nxt = date(q_start.year + (m - 1) // 12, (m - 1) % 12 + 1, 1)
    return nxt - timedelta(days=1)


def in_quarter_end_freeze(d: date, business_days: int, fy_start_month: int) -> tuple[bool, date]:
    qe = quarter_end(d, fy_start_month)
    return business_days_back(qe, business_days) <= d <= qe, qe


# --------------------------------------------------------------------------- planner


class WavePlanner:
    def __init__(self, ctx: PlanningContext, rubrics: RubricSet | None = None, rules: dict[str, Any] | None = None,
                 store: Any = None):
        self.ctx = ctx
        self.rubrics = rubrics or default_rubrics()
        self.rules_doc = rules or load_rules()
        self.rules = {r["rule"]: r for r in self.rules_doc["rules"] if r.get("enabled", True)}
        self.store = store
        self.est = Estimator(ctx, self.rubrics)
        self.team = float(self.rubrics.get("rubric.estimation.team_hours_per_week"))
        r = self.rules.get("max_wave_weeks")
        self.max_weeks = int(self.rubrics.get(r["weeks_threshold_ref"])) if r else None
        self.tags = ctx.tags()
        self._weeks_cache: dict[tuple[str, ...], tuple[int, float]] = {}

    # -- sizing
    def size(self, ids: list[str]) -> tuple[int, float]:
        key = tuple(sorted(ids))
        if key not in self._weeks_cache:
            e = self.est.estimate("sizing", key, cutovers=1)
            self._weeks_cache[key] = (max(1, math.ceil(e.p50_hours / self.team)), e.p50_hours)
        return self._weeks_cache[key]

    def fits(self, ids: list[str]) -> bool:
        return self.max_weeks is None or self.size(ids)[0] <= self.max_weeks

    # -- graph
    def edge_kinds(self) -> set[str]:
        r = self.rules.get("dependency_clusters")
        return set(r["params"]["edge_kinds"]) if r else set()

    def clusters(self, scope: list[str]) -> tuple[list[list[str]], list[str]]:
        kinds = self.edge_kinds()
        edges = self.ctx.edges_within(scope, kinds)
        nbrs: dict[str, set[str]] = defaultdict(set)
        for f, t, _ in edges:
            nbrs[f].add(t)
            nbrs[t].add(f)
        hub_min = int(self.rubrics.get("rubric.gates.waves.hub_degree_min"))
        r = self.rules.get("dependency_clusters")
        hub_types = set(r["params"].get("hub_types", [])) if r else set()
        hubs = sorted(o for o in scope if (len(nbrs[o]) >= hub_min and kinds)
                      or self.ctx.objects[o].object_type in hub_types)
        rest = [o for o in scope if o not in set(hubs)]
        seen: set[str] = set()
        comps = []
        for start in sorted(rest, key=self.ctx.name):
            if start in seen:
                continue
            comp, stack = [], [start]
            seen.add(start)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for n in sorted(nbrs[cur]):
                    if n not in seen and n not in hubs:
                        seen.add(n)
                        stack.append(n)
            comps.append(sorted(comp, key=self.ctx.name))
        return comps, hubs

    def layers(self, ids: list[str]) -> dict[str, int]:
        """Dependency layer: 0 for objects that reference nothing in ``ids``; references come first."""
        refs: dict[str, set[str]] = defaultdict(set)
        for f, t, _ in self.ctx.edges_within(ids, self.edge_kinds() or {"reads", "writes", "calls", "schedules"}):
            refs[f].add(t)
        layer: dict[str, int] = {}

        def depth(o: str, stack: frozenset) -> int:
            if o in layer:
                return layer[o]
            below = [depth(t, stack | {o}) for t in sorted(refs[o]) if t not in stack]
            layer[o] = 1 + max(below) if below else 0
            return layer[o]

        for o in sorted(ids, key=self.ctx.name):
            depth(o, frozenset())
        return layer

    def split(self, cluster: list[str]) -> list[list[str]]:
        if self.fits(cluster):
            return [cluster]
        lay = self.layers(cluster)
        chunks: list[list[str]] = [[]]
        for o in sorted(cluster, key=lambda x: (lay[x], self.ctx.name(x))):
            if chunks[-1] and not self.fits(chunks[-1] + [o]):
                chunks.append([])
            chunks[-1].append(o)
        return chunks

    # -- classification helpers
    def consumable(self, oid: str) -> bool:
        r = self.rules.get("ends_with_business_consumable")
        p = r["params"] if r else {"consumable_types": ["view", "report"], "direct_use_counts": True}
        o = self.ctx.objects[oid]
        return o.object_type in p["consumable_types"] or (p.get("direct_use_counts") and o.usage_90d > 0
                                                          and o.object_type == "table")

    def thin_slice(self, scope: list[str]) -> list[str]:
        """Smallest source → transform → consumer slice that fits one wave.

        For each consumer (view/report) take everything it transitively references plus, for every table
        reached, the processes that populate it (and what they reference) — a vertical slice of one subject
        area rather than a whole cluster or "the easiest tables".
        """
        p = self.rules["thin_vertical_slice_first"]["params"]
        in_scope = set(scope)
        refs: dict[str, set[str]] = defaultdict(set)
        writers: dict[str, set[str]] = defaultdict(set)
        for f, t, k in self.ctx.edges_within(scope, DEPENDENCY_KINDS):
            refs[f].add(t)
            if k == "writes":
                writers[t].add(f)
        best: tuple | None = None
        for c in sorted(scope, key=self.ctx.name):
            if self.ctx.objects[c].object_type not in p["consumer_types"]:
                continue
            closure, stack = {c}, [c]
            while stack:
                cur = stack.pop()
                nxt = refs[cur] | (writers[cur] if self.ctx.objects[cur].object_type == "table" else set())
                for n in sorted(nxt):
                    if n in in_scope and n not in closure:
                        closure.add(n)
                        stack.append(n)
            ids = sorted(closure, key=self.ctx.name)
            if not self.is_vertical_slice(ids) or not self.fits(ids):
                continue
            key = (self.size(ids)[1], len(ids), self.ctx.name(c))
            if best is None or key < best[0]:
                best = (key, ids)
        return best[1] if best else []

    def is_vertical_slice(self, ids: list[str]) -> bool:
        p = self.rules["thin_vertical_slice_first"]["params"]
        types = {self.ctx.objects[i].object_type for i in ids}
        return bool(types & set(p["source_types"])) and bool(types & set(p["transform_types"])) and bool(
            types & set(p["consumer_types"]))

    # -- plan
    def plan(self) -> WavePlan:
        ctx = self.ctx
        scope = ctx.in_scope()
        waves_ids: list[list[str]] = []
        waves_labels: list[list[str]] = []
        groups: list[tuple[str, list[str]]] = []  # (cluster label, ids), already split
        thin = None
        if "thin_vertical_slice_first" in self.rules:
            slice_ids = self.thin_slice(scope)
            if slice_ids:
                thin = SLICE
                waves_ids.append(slice_ids)
                waves_labels.append([SLICE])
                groups.append((SLICE, slice_ids))
        taken = set(waves_ids[0]) if waves_ids else set()
        comps, hubs = self.clusters([o for o in scope if o not in taken])
        for comp in comps:
            label = stable_id("CL", *comp)
            for i, chunk in enumerate(self.split(comp)):
                groups.append((f"{label}.{i + 1}" if len(comp) != len(chunk) else label, chunk))

        value = {lab: sum(ctx.objects[i].usage_90d for i in ids) for lab, ids in groups}
        # business value first (direct usage), keeping split chunks of one cluster in dependency order
        base_value = defaultdict(int)
        for lab, ids in groups:
            base_value[lab.split(".")[0]] += value[lab]
        ordered = sorted((g for g in groups if g[0] != thin),
                         key=lambda g: (-base_value[g[0].split(".")[0]], g[0].split(".")[0],
                                        int(g[0].split(".")[1]) if "." in g[0] else 0))
        current: list[str] = []
        current_labels: list[str] = []
        for lab, ids in ordered:
            if current and not self.fits(current + ids):
                waves_ids.append(current)
                waves_labels.append(current_labels)
                current, current_labels = [], []
            current = current + ids
            current_labels.append(lab)
        if current:
            waves_ids.append(current)
            waves_labels.append(current_labels)

        # WR-05: merge waves without a business consumable into a neighbour when capacity allows
        i = 0
        while i < len(waves_ids):
            if any(self.consumable(o) for o in waves_ids[i]) or len(waves_ids) == 1:
                i += 1
                continue
            start = 1 if thin is not None else 0
            targets = [j for j in (i - 1, i + 1) if start <= j < len(waves_ids) and j != i]
            merged = False
            for j in targets:
                if self.fits(waves_ids[j] + waves_ids[i]):
                    waves_ids[j] = waves_ids[j] + waves_ids[i]
                    waves_labels[j] = waves_labels[j] + waves_labels[i]
                    del waves_ids[i], waves_labels[i]
                    merged = True
                    break
            if not merged:
                i += 1

        # WR-01/06: hubs go where dependency order allows (just in time for their first consumer)
        wave_of = {o: n + 1 for n, ids in enumerate(waves_ids) for o in ids}
        refs = defaultdict(set)
        for f, t, _ in ctx.edges_within(scope, DEPENDENCY_KINDS):
            refs[f].add(t)
        pending = list(hubs)
        for _ in range(len(hubs) + 1):
            progress = False
            for h in list(pending):
                lower = max((wave_of[t] for t in refs[h] if t in wave_of), default=1)
                if any(t in pending for t in refs[h]):
                    continue
                consumers = [f for f in scope if h in refs[f] and f in wave_of]
                upper = min((wave_of[f] for f in consumers), default=None)
                target = upper if upper is not None and upper >= lower else lower
                wave_of[h] = target
                pending.remove(h)
                progress = True
            if not progress:
                break
        for h in pending:  # dependency cycle among hubs: place with their latest reference
            wave_of[h] = max((wave_of.get(t, 1) for t in refs[h]), default=1)
        if not waves_ids and hubs:
            waves_ids.append([])
            waves_labels.append([])
        for h in hubs:
            waves_ids[wave_of[h] - 1].append(h)

        return self._finish(waves_ids, waves_labels, hubs, thin, dict(groups))

    def _finish(self, waves_ids: list[list[str]], waves_labels: list[list[str]], hubs: list[str],
                thin: str | None, clusters: dict[str, list[str]]) -> WavePlan:
        ctx, rs = self.ctx, self.rubrics
        freeze = self.rules.get("quarter_end_freeze")
        fy = int(rs.get("rubric.gates.waves.fiscal_year_start_month"))
        plan_key = canonical_json({"snapshot": ctx.snapshot_id, "rubric": rs.version,
                                   "rules": self.rules_doc["version"], "inputs": ctx.inputs})
        plan_id = stable_id("PLAN", plan_key, length=10)
        start = ctx.start_date()
        programme_inputs = {k: ctx.inputs.get(k) for k in rs.get("rubric.pattern_recommender.inputs")}
        waves: list[Wave] = []
        cursor = start
        for n, ids in enumerate(waves_ids, 1):
            ids = sorted(ids, key=ctx.name)
            weeks, hours = self.size(ids)
            w_start = cursor
            w_end = w_start + timedelta(weeks=weeks) - timedelta(days=1)
            cutover = last_business_day_on_or_before(w_end)
            tags = sorted(set().union(*(self.tags.get(o, set()) for o in ids)) if ids else set())
            notes = []
            shift = 0
            if freeze and set(tags) & set(freeze["applies_to_tags"]):
                days = int(rs.get(freeze["business_days_threshold_ref"]))
                frozen, qe = in_quarter_end_freeze(cutover, days, fy)
                if frozen:
                    new_cutover = next_business_day_after(qe)
                    shift = (new_cutover - cutover).days
                    w_start += timedelta(days=shift)
                    w_end += timedelta(days=shift)
                    cutover = new_cutover
                    notes.append(f"start shifted {shift} days: {', '.join(sorted(set(tags) & set(freeze['applies_to_tags'])))}"
                                 f" objects may not cut over in the last {days} business days of the quarter ending {qe}")
            wave_id = stable_id("WAVE", plan_id, n)
            est = self.est.estimate(wave_id, ids, cutovers=1)
            inputs = {**programme_inputs, **evidence_inputs(ctx, ids, self.tags)}
            rec = recommend(inputs, scope=wave_id, snapshot_id=ctx.snapshot_id, rubrics=rs)
            consumables = [ctx.name(o) for o in ids if self.consumable(o)]
            schemas = Counter(ctx.name(o).split(".")[-2] if ctx.name(o).count(".") >= 1 else ctx.name(o)
                              for o in ids if self.consumable(o)) or Counter(ctx.name(o).split(".")[0] for o in ids)
            subject = schemas.most_common(1)[0][0] if schemas else "shared"
            name = f"Wave {n}{' (thin slice)' if thin and thin in waves_labels[n - 1] else ''}: {subject}"
            notes.insert(0, f"{len(ids)} objects in {len(waves_labels[n - 1])} dependency cluster(s)"
                            + (f" plus {len([h for h in hubs if h in ids])} shared hub object(s)"
                               if any(h in ids for h in hubs) else "")
                            + f"; {weeks} weeks at {self.team:g} h/week (p50 {hours:.1f}h)")
            waves.append(Wave(wave_id, n, name, ids, weeks, est.p50_hours, w_start, w_end, cutover, tags,
                              sorted(consumables), sorted(waves_labels[n - 1]), sorted(h for h in hubs if h in ids),
                              bool(thin and thin in waves_labels[n - 1]), shift, rec.pattern, rec.to_dict(),
                              est.to_dict(), "; ".join(notes)))
            cursor = w_end + timedelta(days=1)
        programme = self.est.estimate("programme", None, include_foundation=True, include_retired=True,
                                      cutovers=len(waves))
        prog_inputs = {**programme_inputs, **evidence_inputs(ctx, ctx.in_scope(), self.tags)}
        prog_rec = recommend(prog_inputs, scope="programme", snapshot_id=ctx.snapshot_id, rubrics=rs)
        plan = WavePlan(plan_id, ctx.engagement_id, ctx.snapshot_id, ctx.assessment.harvest_snapshot_id, rs.version,
                        self.rules_doc["version"], start, waves, sorted(ctx.retired(), key=ctx.name), [], "draft", [],
                        programme.to_dict(), prog_rec.to_dict(),
                        {k: sorted(v, key=ctx.name) for k, v in sorted(clusters.items())}, sorted(hubs, key=ctx.name))
        plan.violations = validate_plan(plan, ctx, self.rules_doc, rs, store=self.store)
        gate_violations = [v for v in plan.violations if v["rule"] == "requires_gate"]
        plan.status = "draft" if plan.violations else "baseline"
        plan.status_reasons = [v["message"] for v in plan.violations] or ["all wave rules satisfied"]
        if gate_violations and len(gate_violations) == len(plan.violations):
            plan.status_reasons.insert(0, "plan is valid but not baselined until the gate passes")
        return plan


# --------------------------------------------------------------------------- validation (rules as data)


def _v(rule: dict[str, Any], message: str, wave: int | None = None) -> dict[str, Any]:
    return {"rule_id": rule["id"], "rule": rule["rule"], "wave": wave, "message": message}


def _rule_dependency_clusters(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    """Linked objects share a wave unless one is a shared hub or both are chunks of one split cluster."""
    out = []
    wave_of = plan.wave_of()
    hubs = set(plan.hubs)
    base = {o: label.split(".")[0] for label, ids in plan.clusters.items() for o in ids}
    sliced = set(plan.clusters.get(SLICE, []))
    for f, t, k in ctx.edges_within(wave_of, set(rule["params"]["edge_kinds"])):
        if f in hubs or t in hubs or f in sliced or t in sliced or wave_of[f] == wave_of[t]:
            continue
        if base.get(f) is None or base.get(f) != base.get(t):
            out.append(_v(rule, f"{ctx.name(f)} and {ctx.name(t)} are linked ({k}) but sit in different clusters "
                                f"(waves {wave_of[f]} and {wave_of[t]})", wave_of[f]))
    return out


def _rule_thin_slice(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    if not plan.waves:
        return []
    p = rule["params"]
    types = {ctx.objects[o].object_type for o in plan.waves[0].object_ids}
    missing = [layer for layer, key in (("source", "source_types"), ("transform", "transform_types"),
                                        ("consumer", "consumer_types")) if not types & set(p[key])]
    if missing:
        return [_v(rule, f"wave 1 is not a vertical slice (no {', '.join(missing)} layer)", 1)]
    return []


def _rule_max_weeks(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    limit = int(rs.get(rule["weeks_threshold_ref"]))
    return [_v(rule, f"wave {w.ordinal} needs {w.weeks} weeks (> {limit})", w.ordinal)
            for w in plan.waves if w.weeks > limit]


def _rule_quarter_freeze(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    days = int(rs.get(rule["business_days_threshold_ref"]))
    fy = int(rs.get("rubric.gates.waves.fiscal_year_start_month"))
    out = []
    for w in plan.waves:
        tagged = set(w.tags) & set(rule["applies_to_tags"])
        if tagged:
            frozen, qe = in_quarter_end_freeze(w.cutover_date, days, fy)
            if frozen:
                out.append(_v(rule, f"wave {w.ordinal} cuts over {w.cutover_date} inside the last {days} business "
                                    f"days of the quarter ending {qe} with {', '.join(sorted(tagged))} objects",
                              w.ordinal))
    return out


def _rule_consumable(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    p = rule["params"]
    out = []
    for w in plan.waves:
        ok = any(ctx.objects[o].object_type in p["consumable_types"]
                 or (p.get("direct_use_counts") and ctx.objects[o].object_type == "table" and ctx.objects[o].usage_90d > 0)
                 for o in w.object_ids)
        if not ok:
            out.append(_v(rule, f"wave {w.ordinal} delivers nothing a business user uses", w.ordinal))
    return out


def _rule_dependency_order(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    wave_of = plan.wave_of()
    out = []
    for f, t, k in ctx.edges_within(wave_of, DEPENDENCY_KINDS):
        if wave_of[t] > wave_of[f]:
            out.append(_v(rule, f"{ctx.name(f)} (wave {wave_of[f]}) depends on {ctx.name(t)} (wave {wave_of[t]}) "
                                f"via {k}", wave_of[f]))
    return out


def _rule_requires_gate(plan: WavePlan, ctx: PlanningContext, rule: dict, rs: RubricSet, store: Any) -> list:
    gate = rule["params"]["gate"]
    if store is None or not gate_passed(store, gate, plan.snapshot_id):
        return [_v(rule, f"gate '{gate}' has not passed on assessment snapshot {plan.snapshot_id}")]
    return []


RULES: dict[str, Callable[..., list]] = {
    "dependency_clusters": _rule_dependency_clusters,
    "thin_vertical_slice_first": _rule_thin_slice,
    "max_wave_weeks": _rule_max_weeks,
    "quarter_end_freeze": _rule_quarter_freeze,
    "ends_with_business_consumable": _rule_consumable,
    "dependency_order": _rule_dependency_order,
    "requires_gate": _rule_requires_gate,
}


def validate_plan(plan: WavePlan, ctx: PlanningContext, rules: dict[str, Any] | None = None,
                  rubrics: RubricSet | None = None, store: Any = None) -> list[dict[str, Any]]:
    rules = rules or load_rules()
    rubrics = rubrics or default_rubrics()
    out: list[dict[str, Any]] = []
    for rule in rules["rules"]:
        if rule.get("enabled", True):
            out.extend(RULES[rule["rule"]](plan, ctx, rule, rubrics, store))
    return out


# --------------------------------------------------------------------------- persistence


def record_plan(store: Any, plan: WavePlan, ctx: PlanningContext) -> None:
    """Persist waves, wave objects (factory state ``classified``), estimates and recommendations (idempotent)."""
    from .factory import Factory

    if store.get("wave_plan", plan_id=plan.plan_id):
        return
    eng = plan.engagement_id or ""
    factory = Factory(store)
    conf = {r["object_id"]: float(r["confidence"]) for r in ctx.assessment.rows("object_disposition")}
    for w in plan.waves:
        store.insert("wave", {"wave_id": w.wave_id, "engagement_id": eng, "ordinal": w.ordinal, "name": w.name,
                              "pattern": w.pattern, "start_date": w.start_date, "end_date": w.end_date,
                              "rationale": w.rationale})
        for oid in w.object_ids:
            factory.enrol(w.wave_id, oid, evidence_ref=f"snapshot:{plan.snapshot_id}", confidence=conf.get(oid, 1.0))
        record_estimate(store, Estimate(**w.estimate))
        record_recommendation(store, Recommendation(**w.recommendation), eng)
    record_estimate(store, Estimate(**plan.programme_estimate))
    record_recommendation(store, Recommendation(**plan.programme_recommendation), eng)
    store.insert("wave_plan", {"plan_id": plan.plan_id, "engagement_id": plan.engagement_id,
                               "assessment_snapshot_id": plan.snapshot_id,
                               "harvest_snapshot_id": plan.harvest_snapshot_id, "rubric_version": plan.rubric_version,
                               "rules_version": plan.rules_version, "status": plan.status,
                               "start_date": plan.start_date, "waves": len(plan.waves),
                               "violations": canonical_json(plan.violations),
                               "plan": canonical_json(plan.to_dict())})
