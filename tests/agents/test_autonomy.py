"""M10 acceptance: L2 never executes without approval; L3 only within the pre-approved catalogue and blast
radius, with audit and automatic rollback when the guard metric regresses."""

import copy

import pytest

from altitude.core.errors import ApprovalRequired
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude_agents.actions import ActionGateway, ProposedAction
from altitude_agents.catalogue import ActionCatalogue, load_tenant_policy
from altitude_agents.errors import ActionRefused, AutonomyViolation
from altitude_agents.executor import SimulatedSnowflake
from altitude_agents.runtime import AgentRunner
from altitude_agents.telemetry import Telemetry

from .conftest import CLOCK, clock


def _runner(store, **kw):
    return AgentRunner(store, clock=clock, **kw)


def _status_seq(gw, action_id):
    return [(r["seq"], r["status"]) for r in gw.log.history(action_id)]


# --------------------------------------------------------------------------- L2
def test_l2_actions_never_execute_without_recorded_approval(seeded_tel):
    store = Store()
    runner = _runner(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-ACCESS-HYGIENE", seeded_tel, executor=sim, require_promoted=False)
    assert report.actions and all(a.autonomy == "L2" and a.status == "proposed" for a in report.actions)
    assert sim.executed == []  # an executor was available, yet nothing ran

    gw = runner.gateway
    disable = report.action("user.disable", "OLD_ANALYST")
    with pytest.raises(ApprovalRequired):
        gw.execute(disable.action_id, sim)
    assert sim.current("user", "OLD_ANALYST")["disabled"] is False

    # forging an 'approved' status row without an approval record does not help
    first = gw.log.first(disable.action_id)
    gw.log.append(action_id=disable.action_id, run_id=first["run_id"], agent_id=first["agent_id"], autonomy="L2",
                  action_type=first["action_type"], target=first["target"], payload={}, status="approved",
                  actor="someone")
    with pytest.raises(ApprovalRequired):
        gw.execute(disable.action_id, sim)
    assert sim.executed == []


def test_l2_approval_rules_and_execution_trail(seeded_tel):
    store = Store()
    runner = _runner(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-ACCESS-HYGIENE", seeded_tel, require_promoted=False)
    gw = runner.gateway
    revoke = report.action("grant.revoke_role_from_user", "JSMITH")
    with pytest.raises(ApprovalRequired):          # agents never approve agent actions
        gw.approve(revoke.action_id, "SVC_ALT_ACCESS_HYGIENE")
    with pytest.raises(ApprovalRequired):          # owner approval required (tenant approvers as data)
        gw.approve(revoke.action_id, "random.analyst", approver_role="analyst")
    gw.approve(revoke.action_id, "alice", approver_role="security-owner", comment="confirmed with JSMITH's manager")
    rec = gw.execute(revoke.action_id, sim)
    assert rec.status == "executed"
    assert sim.executed == ["REVOKE ROLE ACCOUNTADMIN FROM USER JSMITH"]
    assert not sim.rows("SELECT * FROM GRANTS_TO_USERS WHERE GRANTEE_NAME='JSMITH' AND ROLE='ACCOUNTADMIN'")
    assert _status_seq(gw, revoke.action_id) == [(1, "proposed"), (2, "approved"), (3, "executed")]
    executed = gw.log.latest(revoke.action_id)
    assert executed["actor"] == "alice"
    assert gw.approvals(revoke.action_id)[0]["approver"] == "alice"
    with pytest.raises(ActionRefused):             # an executed action cannot run twice
        gw.execute(revoke.action_id, sim)

    # a rejected draft can never execute
    mfa = report.action("user.set_authentication_policy", "TEMP_CONTRACTOR")
    gw.reject(mfa.action_id, "alice", approver_role="security-owner", comment="user leaving")
    with pytest.raises(ActionRefused, match="rejected"):
        gw.execute(mfa.action_id, sim)
    with pytest.raises(ActionRefused):
        gw.approve(mfa.action_id, "bob", approver_role="security-owner")


def test_recommendations_and_drafts_are_not_executable(seeded_tel):
    store = Store()
    runner = _runner(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-ACCESS-HYGIENE", seeded_tel, require_promoted=False)
    rec_rows = store.query("SELECT action_id FROM agent_action WHERE action_type='recommendation'")
    assert rec_rows  # service-password / orphan-role recommendations (L1)
    with pytest.raises((ActionRefused, AutonomyViolation)):
        runner.gateway.execute(rec_rows[0]["action_id"], sim)
    triage = runner.run("AG-PIPELINE-TRIAGE", seeded_tel, require_promoted=False)
    fix = triage.action("task.fix_draft", "EDW.STAGING.INGEST_EVENTS_TASK")
    runner.gateway.approve(fix.action_id, "pat", approver_role="pipeline-owner")
    with pytest.raises(ActionRefused, match="draft"):
        runner.gateway.execute(fix.action_id, sim)
    assert sim.executed == [] and report.actions


def test_agent_cannot_draft_outside_its_action_types(seeded_tel):
    store = Store()
    runner = _runner(store)
    spec = runner.agents["AG-COST-SENTINEL"]
    with pytest.raises(AutonomyViolation):
        runner.gateway.propose("RUN-X", spec, ProposedAction("warehouse.resize", "WH_DS", {"warehouse_size": "SMALL"},
                                                             "L3", 0.99, "cost sentinel is L1"))


# --------------------------------------------------------------------------- L3
def test_l3_executes_pre_approved_actions_with_audit(seeded_tel):
    store = Store()
    runner = _runner(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-WAREHOUSE-RIGHTSIZER", seeded_tel, executor=sim, require_promoted=False)
    executed = [a for a in report.actions if a.status == "executed"]
    assert {a.target for a in executed} == {"WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"}
    assert all(a.autonomy == "L3" and a.action_type == "warehouse.set_auto_suspend" for a in executed)
    assert sim.warehouse("WH_DEV")["AUTO_SUSPEND"] == 60
    # size / cluster changes stayed drafts
    assert {a.action_type for a in report.actions if a.status == "proposed"} == {
        "warehouse.resize", "warehouse.set_max_cluster_count"}
    assert sim.warehouse("WH_BI_ADHOC")["WAREHOUSE_SIZE"] == "LARGE"
    # audit + rollback payload captured
    row = runner.gateway.log.latest(executed[0].action_id)
    assert row["actor"] == "SVC_ALT_RIGHTSIZER" and "AUTO_SUSPEND" in row["rollback_payload"]
    assert store.query("SELECT * FROM audit_event WHERE action='agent_action.executed'")


def _custom_catalogue(mutate):
    cat = ActionCatalogue.load()
    doc_types = [t for t in cat.types.values()]
    pre = list(cat.pre_approved)
    out = ActionCatalogue({t.action_type: t for t in doc_types}, [p for p in pre])
    mutate(out)
    return out


def test_uncatalogued_l3_action_is_refused_and_logged(seeded_tel):
    store = Store()
    cat = _custom_catalogue(lambda c: c.pre_approved.clear())   # tenant has pre-approved nothing
    runner = _runner(store, action_catalogue=cat)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-WAREHOUSE-RIGHTSIZER", seeded_tel, executor=sim, require_promoted=False)
    assert sim.executed == []
    assert {r["target"] for r in report.refused} == {"WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"}
    assert all("pre-approved action catalogue" in r["reason"] for r in report.refused)
    for r in report.refused:
        assert _status_seq(runner.gateway, r["action_id"]) == [(1, "proposed"), (2, "rejected")]
    # the refused change was re-drafted at L2 for a human
    drafts = [a for a in report.actions if a.action_type == "warehouse.set_auto_suspend" and a.status == "proposed"]
    assert {a.target for a in drafts} == {"WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"}
    assert all(a.autonomy == "L2" for a in drafts)


def _gateway(store, rubrics=None, catalogue=None):
    return ActionGateway(store, load_tenant_policy("default"), catalogue or ActionCatalogue.load(),
                         rubrics=rubrics or default_rubrics(), clock=clock)


def _start_run(store, run_id="RUN-T1"):
    store.insert("agent_run", {"run_id": run_id, "agent_id": "AG-WAREHOUSE-RIGHTSIZER", "agent_version": "1.0.0",
                               "tenant_id": "default", "trigger": "test", "started_at": CLOCK, "status": "running"})
    return run_id


def _propose(gw, run_id, target, value, agent="AG-WAREHOUSE-RIGHTSIZER"):
    return gw.propose(run_id, gw.agents[agent], ProposedAction(
        "warehouse.set_auto_suspend", target, {"auto_suspend": value}, "L3", 0.95, "test"))


@pytest.mark.parametrize("target,value,reason", [
    ("WH_DEV", 7200, "blast-radius bounds"),      # parameter above the catalogue's max
    ("WH_DEV", 5, "blast-radius bounds"),         # parameter below the catalogue's min
    ("WH_ELT_PROD", 60, "outside the pre-approved scope"),
])
def test_over_blast_radius_or_out_of_scope_is_refused(seeded_tel, target, value, reason):
    store = Store()
    gw = _gateway(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    rec = _propose(gw, _start_run(store), target, value)
    assert rec.autonomy == "L3"
    with pytest.raises(ActionRefused, match=reason):
        gw.execute(rec.action_id, sim, seeded_tel)
    assert sim.executed == []
    assert gw.get(rec.action_id).status == "rejected"


def test_per_run_and_per_day_limits(seeded_tel):
    store = Store()
    rubrics = default_rubrics().with_overrides({"agents": {"blast_radius": {"auto_suspend_targets_per_run": 2,
                                                                            "auto_suspend_executions_per_day": 3}}})
    gw = _gateway(store, rubrics)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    run = _start_run(store)
    a, b, c = (_propose(gw, run, w, 60) for w in ("WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"))
    gw.execute(a.action_id, sim, seeded_tel)
    gw.execute(b.action_id, sim, seeded_tel)
    with pytest.raises(ActionRefused, match="already executed on 2"):
        gw.execute(c.action_id, sim, seeded_tel)
    run2 = _start_run(store, "RUN-T2")
    d = _propose(gw, run2, "WH_DEV", 60)
    gw.execute(d.action_id, sim, seeded_tel)               # 3rd today: allowed
    e = _propose(gw, run2, "WH_AGENTS", 120)
    with pytest.raises(ActionRefused, match="daily limit"):
        gw.execute(e.action_id, sim, seeded_tel)
    assert len(sim.executed) == 3


def test_change_window_closed_refuses(seeded_tel):
    store = Store()
    cat = _custom_catalogue(lambda c: None)
    entry = cat.pre_approved[0]
    cat.pre_approved[0] = type(entry)(**{**entry.__dict__, "change_window": {"days": ["SAT", "SUN"],
                                                                             "start_hour_utc": 0, "end_hour_utc": 24}})
    gw = _gateway(store, catalogue=cat)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)   # CLOCK is a Thursday
    rec = _propose(gw, _start_run(store), "WH_DEV", 60)
    with pytest.raises(ActionRefused, match="change window"):
        gw.execute(rec.action_id, sim, seeded_tel)


def test_rerun_requires_idempotent_flag_in_data(seeded_tel):
    store = Store()
    gw = _gateway(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    run = _start_run(store)
    spec = gw.agents["AG-PIPELINE-TRIAGE"]
    ok = gw.propose(run, spec, ProposedAction("task.rerun", "EDW.SALES.LOAD_ORDERS_TASK", {}, "L3", 0.9, "transient"))
    gw.execute(ok.action_id, sim, seeded_tel)
    assert sim.executed == ["EXECUTE TASK EDW.SALES.LOAD_ORDERS_TASK"]
    bad = gw.propose(run, spec, ProposedAction("task.rerun", "EDW.FINANCE.LOAD_REVENUE_TASK", {}, "L3", 0.9, "x"))
    with pytest.raises(ActionRefused, match="idempotent"):
        gw.execute(bad.action_id, sim, seeded_tel)
    assert len(sim.executed) == 1


def test_low_confidence_output_never_runs_unattended(seeded_tel):
    store = Store()
    gw = _gateway(store)
    rec = gw.propose(_start_run(store), gw.agents["AG-WAREHOUSE-RIGHTSIZER"], ProposedAction(
        "warehouse.set_auto_suspend", "WH_DEV", {"auto_suspend": 60}, "L3", 0.5, "weak evidence"),
        needs_review=True, review_subject=("agent_finding", "x"))
    assert rec.autonomy == "L2"


def test_tenant_cap_limits_autonomy(seeded_tel):
    store = Store()
    runner = AgentRunner(store, tenant_id="cautious", clock=clock)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-WAREHOUSE-RIGHTSIZER", seeded_tel, executor=sim, require_promoted=False)
    assert sim.executed == [] and all(a.autonomy == "L2" for a in report.actions)


def test_never_deletes_data_guardrail(seeded_tel):
    store = Store()
    cat = ActionCatalogue.load()
    from altitude_agents.catalogue import ActionType
    cat.types["table.quarantine"] = ActionType("table.quarantine", "table", {"tag": "identifier", "reason": "text"},
                                               "DELETE FROM {target} WHERE 1=1", None, (), False, True, False)
    gw = _gateway(store, catalogue=cat)
    with pytest.raises(ActionRefused, match="forbidden"):
        gw.propose("RUN-Q", gw.agents["AG-DQ-INCIDENT"], ProposedAction(
            "table.quarantine", "EDW.SALES.FCT_ORDERS", {"tag": "GOVERNANCE.TAGS.DQ_STATUS", "reason": "x"}, "L2",
            0.9, "bad template"))
    assert store.scalar("SELECT count(*) FROM agent_action") == 0


# --------------------------------------------------------------------------- auto-rollback
def _with_queueing(tables, warehouse, queued):
    t = copy.deepcopy(tables)
    last_day = max(r["START_TIME"] for r in t["WAREHOUSE_LOAD_HISTORY"]).date()
    for r in t["WAREHOUSE_LOAD_HISTORY"]:
        if r["WAREHOUSE_NAME"] == warehouse and r["START_TIME"].date() == last_day:
            r["AVG_QUEUED_PROVISIONING"] = queued
    return t


def test_auto_rollback_when_guard_metric_regresses(seeded_tables, seeded_tel):
    store = Store()
    gw = _gateway(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    assert sim.warehouse("WH_DEV")["AUTO_SUSPEND"] == 3600
    rec = _propose(gw, _start_run(store), "WH_DEV", 60)
    rec = gw.execute(rec.action_id, sim, seeded_tel)
    assert rec.status == "executed" and sim.warehouse("WH_DEV")["AUTO_SUSPEND"] == 60
    assert rec.payload["guard"]["baseline"] == 0.0

    after = Telemetry.from_tables(_with_queueing(seeded_tables, "WH_DEV", 0.9))   # cold starts now queue queries
    result = gw.check_guard(rec.action_id, after, sim)
    assert result.regressed and result.observed > result.baseline + result.tolerance
    assert sim.warehouse("WH_DEV")["AUTO_SUSPEND"] == 3600                      # reverted
    assert sim.executed == ["ALTER WAREHOUSE WH_DEV SET AUTO_SUSPEND = 60",
                            "ALTER WAREHOUSE WH_DEV SET AUTO_SUSPEND = 3600"]
    hist = gw.log.history(rec.action_id)
    assert [h["status"] for h in hist] == ["proposed", "executed", "rolled_back"]
    last = gw.log.payload(hist[-1])
    assert last["automatic"] is True and "regressed" in last["rollback_reason"]
    assert store.query("SELECT * FROM audit_event WHERE action='agent_action.rolled_back'")


def test_guard_ok_keeps_change(seeded_tables, seeded_tel):
    store = Store()
    gw = _gateway(store)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    rec = gw.execute(_propose(gw, _start_run(store), "WH_DEV", 60).action_id, sim, seeded_tel)
    result = gw.check_guard(rec.action_id, Telemetry.from_tables(_with_queueing(seeded_tables, "WH_DEV", 0.05)), sim)
    assert not result.regressed
    assert gw.get(rec.action_id).status == "executed" and sim.warehouse("WH_DEV")["AUTO_SUSPEND"] == 60
    assert store.query("SELECT * FROM audit_event WHERE action='agent_action.guard_ok'")
