"""Acceptance (M4, part 2): the wave plan respects the gate/wave rules stored as data; the factory state
machine records every transition with actor, timestamp, evidence and confidence."""

import copy
import json
from datetime import date, datetime

import pytest

from altitude.assessment import record
from altitude.cli import main
from altitude.core.ai import ReviewQueue
from altitude.core.errors import AppendOnlyViolation, ApprovalRequired
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude.planning import Factory, InvalidTransition, WavePlanner, evaluate_gate, record_gate, record_plan, \
    validate_plan
from altitude.planning.waves import in_quarter_end_freeze, load_rules, quarter_end

SMALL_TEAM = {"estimation": {"team_hours_per_week": 6}}  # forces several waves on the small fixture estates


def _non_gate(violations):
    return [v for v in violations if v["rule"] != "requires_gate"]


def _check_rules(plan, ctx, rs):
    """Independent re-check of the Section 9.3 rules against the finished plan."""
    max_weeks = rs.get("rubric.gates.waves.max_weeks_per_wave")
    freeze_days = rs.get("rubric.gates.waves.quarter_end_freeze_business_days")
    wave_of = plan.wave_of()
    assert set(wave_of) == set(ctx.in_scope())  # every kept/rewritten object is planned exactly once
    assert not set(wave_of) & set(ctx.retired())  # retired objects are decommissioned, not migrated
    for w in plan.waves:
        assert w.weeks <= max_weeks
        assert w.consumables, f"wave {w.ordinal} has nothing a business user uses"
        if set(w.tags) & {"regulatory", "month_end"}:
            assert not in_quarter_end_freeze(w.cutover_date, freeze_days, 1)[0]
        assert w.cutover_date.weekday() < 5 and w.start_date <= w.cutover_date <= w.end_date
    for f, t, _ in ctx.edges_within(wave_of, {"reads", "writes", "calls", "schedules"}):
        assert wave_of[t] <= wave_of[f], (ctx.name(f), ctx.name(t))
    first = {ctx.objects[o].object_type for o in plan.waves[0].object_ids}
    assert plan.waves[0].thin_slice and first & {"table"} and first & {"view", "report"}
    assert first & {"procedure", "etl_job", "script", "macro", "package", "function", "schedule"}


@pytest.mark.parametrize("source", ["sqlserver", "oracle", "teradata"])
def test_wave_plan_respects_rules_stored_as_data(ctx_for, source):
    rs = default_rubrics().with_overrides(SMALL_TEAM)
    ctx = ctx_for(source)
    plan = WavePlanner(ctx, rs).plan()
    assert _non_gate(plan.violations) == []
    assert plan.status == "draft" and any("assess_exit" in r for r in plan.status_reasons)  # WR-07: no gate yet
    _check_rules(plan, ctx, rs)
    assert plan.rubric_version == rs.version and plan.rules_version == load_rules()["version"]
    assert all(w.estimate["rubric_version"] == rs.version and w.recommendation["pattern"] == w.pattern
               for w in plan.waves)


def test_wave_plan_is_reproducible_and_thin_slice_first(ctx_for):
    rs = default_rubrics().with_overrides(SMALL_TEAM)
    a = WavePlanner(ctx_for(), rs).plan()
    b = WavePlanner(ctx_for(), rs).plan()
    assert json.dumps(a.to_dict(), default=str, sort_keys=True) == json.dumps(b.to_dict(), default=str, sort_keys=True)
    ctx = ctx_for()
    sizes = [len(w.object_ids) for w in a.waves]
    assert len(a.waves) >= 2 and sizes[0] < max(sizes)  # wave 1 is thin, not the biggest bucket
    first = {ctx.name(o) for o in a.waves[0].object_ids}
    assert "SalesDW.dbo.FactSales" in first and "SalesDW.etl.usp_LoadFactSales" in first  # source → transform → BI
    assert a.waves[0].name.startswith("Wave 1 (thin slice)")
    # clusters come from the lineage graph: the month-end view sits with the table it reads, not by schema name
    wave_of = a.wave_of()
    by = {ctx.name(o): o for o in ctx.objects}
    assert wave_of[by["SalesDW.rpt.vw_MonthEnd"]] == wave_of[by["SalesDW.rpt.MonthEndClose"]]


def test_quarter_end_freeze_rule_moves_cutover(ctx_for):
    rs = default_rubrics().with_overrides(SMALL_TEAM)
    plan = WavePlanner(ctx_for(), rs).plan()
    shifted = [w for w in plan.waves if w.freeze_shift_days]
    assert shifted, "fixture is arranged so a month-end wave would land in the Q1 freeze"
    w = shifted[0]
    assert set(w.tags) & {"month_end", "regulatory"} and "may not cut over" in w.rationale
    assert w.cutover_date == date(2027, 4, 1)  # first business day after the quarter ending 2027-03-31
    # the same plan with the rule disabled in data cuts over inside the freeze → proves the rule moved it
    rules = copy.deepcopy(load_rules())
    for r in rules["rules"]:
        if r["rule"] == "quarter_end_freeze":
            r["enabled"] = False
    free = WavePlanner(ctx_for(), rs, rules=rules).plan()
    same = next(x for x in free.waves if x.ordinal == w.ordinal)
    assert in_quarter_end_freeze(same.cutover_date, rs.get("rubric.gates.waves.quarter_end_freeze_business_days"), 1)[0]
    assert validate_plan(free, ctx_for(), load_rules(), rs)  # ...which the full rule set flags


def test_max_wave_weeks_comes_from_rubric_and_splits_large_clusters(ctx_for):
    tight = default_rubrics().with_overrides({"estimation": {"team_hours_per_week": 5}})
    plan = WavePlanner(ctx_for(), tight).plan()
    assert all(w.weeks <= 12 for w in plan.waves)
    assert any("." in label for label in plan.clusters), "a cluster too large for one wave is split by layer"
    assert _non_gate(plan.violations) == []
    _check_rules(plan, ctx_for(), tight)
    loose_rs = tight.with_overrides({"gates": {"waves": {"max_weeks_per_wave": 26}}})
    loose = WavePlanner(ctx_for(), loose_rs).plan()
    assert len(loose.waves) < len(plan.waves) and all(w.weeks <= 26 for w in loose.waves)
    assert loose.rubric_version != plan.rubric_version
    _check_rules(loose, ctx_for(), loose_rs)


def test_validate_plan_flags_broken_rules(ctx_for):
    rs = default_rubrics().with_overrides(SMALL_TEAM)
    ctx = ctx_for()
    plan = WavePlanner(ctx, rs).plan()
    broken = copy.deepcopy(plan)
    # move a producer after its consumer and swap the thin slice for a later wave
    by = {ctx.name(o): o for o in ctx.objects}
    fact = by["SalesDW.dbo.FactSales"]
    broken.waves[0].object_ids.remove(fact)
    broken.waves[-1].object_ids.append(fact)
    broken.waves[-1].weeks = 99
    rules = {v["rule"] for v in validate_plan(broken, ctx, load_rules(), rs)}
    assert {"dependency_order", "max_wave_weeks", "requires_gate"} <= rules


def test_plan_baselined_only_after_gate_and_factory_records_transitions(estates, ctx_for):
    harvest, assessment = estates["sqlserver"]
    rs = default_rubrics().with_overrides(SMALL_TEAM)
    store = Store()
    record(assessment, store)
    q = ReviewQueue(store)
    for item in q.open_items("object_disposition"):
        q.decide(item["item_id"], "lead.architect", "approved")
    eng = assessment.summary["engagement_id"]
    from altitude.planning import collect_metrics

    m = collect_metrics(assessment=assessment, store=store,
                        facts={"tier1_identified": True, "business_case_approved": True})
    record_gate(store, evaluate_gate("assess_exit", m, snapshot_id=assessment.snapshot_id, engagement_id=eng))
    ctx = ctx_for()
    plan = WavePlanner(ctx, rs, store=store).plan()
    assert plan.violations == [] and plan.status == "baseline"
    record_plan(store, plan, ctx)
    record_plan(store, plan, ctx)  # idempotent
    assert store.scalar("SELECT count(*) FROM wave") == len(plan.waves)
    assert store.scalar("SELECT count(*) FROM wave_object") == len(ctx.in_scope())
    assert store.scalar("SELECT count(*) FROM wave_object WHERE state = 'classified'") == len(ctx.in_scope())
    assert store.scalar("SELECT count(*) FROM estimate") == len(plan.waves) + 1
    assert store.scalar("SELECT count(*) FROM pattern_recommendation") == len(plan.waves) + 1
    assert store.get("wave_plan", plan_id=plan.plan_id)["status"] == "baseline"

    f = Factory(store, rs)
    w1 = plan.waves[0]
    oid = next(o for o in w1.object_ids if ctx.objects[o].object_type == "procedure")
    hist = f.history(oid, w1.wave_id)
    assert [(h["from_state"], h["to_state"]) for h in hist] == [("discovered", "classified")]
    assert hist[0]["evidence_ref"] == f"snapshot:{assessment.snapshot_id}"

    with pytest.raises(InvalidTransition):
        f.transition(w1.wave_id, oid, "cut_over", actor="eng1", actor_type="human", evidence_ref="x", confidence=1)
    at = datetime(2026, 11, 3, 10)
    f.transition(w1.wave_id, oid, "converted", actor="snowconvert", actor_type="system",
                 evidence_ref="conversion_run:CR-1", confidence=0.9, at=at)
    f.transition(w1.wave_id, oid, "ai_remediated", actor="agent:remediator", actor_type="agent",
                 evidence_ref="ai_change:AC-1", confidence=0.91, at=at)
    with pytest.raises(ApprovalRequired):  # review is human-only
        f.transition(w1.wave_id, oid, "reviewed", actor="agent:remediator", actor_type="agent",
                     evidence_ref="review:R-1", confidence=0.99)
    f.transition(w1.wave_id, oid, "reviewed", actor="eng.lead", actor_type="human", evidence_ref="review:R-1",
                 confidence=1.0, at=at)
    with pytest.raises(ApprovalRequired):  # low-confidence agent transition needs a human
        f.transition(w1.wave_id, oid, "unit_tested", actor="agent:tester", actor_type="agent",
                     evidence_ref="test_run:T-1", confidence=0.5)
    for state, ev in [("unit_tested", "test_run:T-1"), ("loaded", "load_job:L-1"), ("reconciled", "validation_run:V-1"),
                      ("performance_tested", "bench:B-1")]:
        f.transition(w1.wave_id, oid, state, actor="agent:runner", actor_type="agent", evidence_ref=ev,
                     confidence=0.95, at=at)
    f.transition(w1.wave_id, oid, "uat_passed", actor="biz.owner", actor_type="human", evidence_ref="uat:U-1",
                 confidence=1.0, at=at)
    with pytest.raises(ApprovalRequired):  # cutover needs a passing cutover_go gate
        f.transition(w1.wave_id, oid, "cut_over", actor="exec", actor_type="human", evidence_ref="gng:G-1",
                     confidence=1.0)
    cut = evaluate_gate("cutover_go", {"tier1_l3_mismatches_unaccepted": 0, "consecutive_clean_parallel_cycles": 2,
                                       "rollback_rehearsed": True, "grants_mapped_pct": 100},
                        snapshot_id=assessment.snapshot_id, engagement_id=eng)
    record_gate(store, cut)
    f.transition(w1.wave_id, oid, "cut_over", actor="exec", actor_type="human", evidence_ref="gng:G-1",
                 confidence=1.0, at=at)
    assert f.state(w1.wave_id, oid) == "cut_over"
    hist = f.history(oid, w1.wave_id)
    assert [h["seq"] for h in hist] == list(range(1, len(hist) + 1))
    assert all(h["actor"] and h["actor_type"] and h["evidence_ref"] and h["recorded_at"] is not None
               and h["confidence"] is not None for h in hist)
    assert f.board(w1.wave_id)["cut_over"] == 1
    assert store.scalar("SELECT count(*) FROM audit_event WHERE action = 'factory.transition'") >= len(hist)
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE factory_transition SET actor = 'someone else'")
    with pytest.raises(AppendOnlyViolation):
        store.execute("DELETE FROM factory_transition")
    # retire path only applies to objects the assessment retired
    keep = next(o for o in w1.object_ids if o != oid)
    with pytest.raises(InvalidTransition):
        f.transition(w1.wave_id, keep, "legacy_retired", actor="eng", actor_type="human", evidence_ref="x",
                     confidence=1.0)


def test_calendar_helpers():
    assert quarter_end(date(2027, 3, 20), 1) == date(2027, 3, 31)
    assert quarter_end(date(2027, 3, 20), 7) == date(2027, 3, 31)
    assert quarter_end(date(2026, 8, 5), 2) == date(2026, 10, 31)  # fiscal year starting in February
    assert in_quarter_end_freeze(date(2027, 3, 18), 10, 1)[0]
    assert not in_quarter_end_freeze(date(2027, 3, 17), 10, 1)[0]


def test_cli_plan_commands(estates, tmp_path, capsys):
    harvest, assessment = estates["teradata"]
    store = str(tmp_path / "store.duckdb")
    inputs = json.dumps({"deadline_weeks": 30, "start_date": "2026-11-02"})
    rc = main(["plan", "waves", "--assessment", str(assessment.snapshot.path), "--harvest", str(harvest.path),
               "--inputs", inputs, "--store", store, "--out", str(tmp_path / "plan.json")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "draft" and out["waves"] and (tmp_path / "plan.json").exists()
    assert main(["plan", "estimate", "--assessment", str(assessment.snapshot.path), "--harvest",
                 str(harvest.path)]) == 0
    est = json.loads(capsys.readouterr().out)
    assert est["rubric_version"] == default_rubrics().version
    assert main(["plan", "recommend", "--assessment", str(assessment.snapshot.path), "--harvest",
                 str(harvest.path), "--inputs", inputs]) == 0
    assert json.loads(capsys.readouterr().out)["pattern"]
    rc = main(["plan", "gate", "assess_exit", "--assessment", str(assessment.snapshot.path), "--store", store,
               "--facts", json.dumps({"tier1_identified": True, "business_case_approved": True})])
    decision = json.loads(capsys.readouterr().out)
    assert rc == (0 if decision["result"] == "pass" else 4)
    plan = json.loads((tmp_path / "plan.json").read_text())
    w = plan["waves"][0]
    rc = main(["plan", "transition", "--store", store, "--wave", w["wave_id"], "--object", w["object_ids"][0],
               "--to", "converted", "--actor", "eng1", "--evidence", "conversion_run:CR-9", "--confidence", "0.9"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["to_state"] == "converted"
