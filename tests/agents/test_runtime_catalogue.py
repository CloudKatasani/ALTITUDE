"""Catalogue integrity, scoped read-only tools, inference logging and executors."""

import pytest

from altitude.core.errors import ReadOnlyViolation
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude_agents.actions import GUARD_METRICS
from altitude_agents.agents import AGENTS
from altitude_agents.catalogue import ActionCatalogue, level_rank, load_agent_catalogue, load_tenant_policy
from altitude_agents.errors import ActionRefused, ToolScopeViolation, UnsupportedStatement
from altitude_agents.executor import LiveExecutor, SimulatedSnowflake, render_sql
from altitude_agents.runtime import AgentRunner, BaseAgent, AgentResult
from altitude_agents.tools import TOOLS

from .conftest import clock


def test_catalogue_has_16_agents_with_distinct_identities_and_minimal_scopes():
    cat = load_agent_catalogue()
    assert sorted(a.number for a in cat.values()) == list(range(1, 17))
    users = [a.service_user for a in cat.values()]
    roles = [a.service_role for a in cat.values()]
    assert len(set(users)) == 16 and len(set(roles)) == 16
    assert {a.agent_id for a in cat.values() if a.implemented} == set(AGENTS)
    actions = ActionCatalogue.load()
    for a in cat.values():
        if a.implemented:
            assert set(a.tool_scope) <= set(TOOLS), a.agent_id
            assert AGENTS[a.agent_id].version == a.version
        assert set(a.action_types) <= set(actions.types), a.agent_id
        for t, lvl in a.autonomy_by_action.items():
            assert t in a.action_types and level_rank(lvl) <= level_rank(a.max_autonomy)
    # read-only agents hold no action types
    assert cat["AG-COST-SENTINEL"].action_types == () and cat["AG-RELEASE-CHANGE-WATCHER"].action_types == ()


def test_pre_approved_catalogue_is_safe_by_construction():
    actions = ActionCatalogue.load()
    agents = load_agent_catalogue()
    rubrics = default_rubrics()
    for p in actions.pre_approved:
        t = actions.types[p.action_type]
        assert t.executable
        assert t.reversible or (p.requires_idempotent_flag or t.idempotent_required), p.entry_id
        if p.rollback == "automatic":
            assert t.rollback_template and p.guard and p.guard["metric"] in GUARD_METRICS
        for a in p.agents:
            assert p.action_type in agents[a].action_types
            assert level_rank(agents[a].action_autonomy(p.action_type)) >= level_rank(p.max_autonomy)
        for ref in [v for k, v in p.blast_radius.items() if k.endswith("_ref")]:
            assert rubrics.has(ref)


def test_templates_validate_values():
    assert render_sql("ALTER WAREHOUSE {target} SET AUTO_SUSPEND = {auto_suspend}", "WH_X", {"auto_suspend": 60},
                      {"auto_suspend": "integer"}) == "ALTER WAREHOUSE WH_X SET AUTO_SUSPEND = 60"
    for target, params in (("WH_X; DROP TABLE T", {"auto_suspend": 60}), ("WH_X", {"auto_suspend": "60; DROP"})):
        with pytest.raises(ActionRefused):
            render_sql("ALTER WAREHOUSE {target} SET AUTO_SUSPEND = {auto_suspend}", target, params,
                       {"auto_suspend": "integer"})


class Snoop(BaseAgent):
    agent_id = "AG-COST-SENTINEL"

    def run(self, ctx):
        ctx.call("users")   # not in the Cost Sentinel's scope
        return AgentResult()


def test_tools_are_scoped_and_telemetry_is_read_only(seeded_tel):
    store = Store()
    runner = AgentRunner(store, clock=clock)
    with pytest.raises(ToolScopeViolation):
        runner.run("AG-COST-SENTINEL", seeded_tel, agent=Snoop(), require_promoted=False)
    assert store.query("SELECT status FROM agent_run")[0]["status"] == "failed"
    for sql in ("DELETE FROM USERS", "UPDATE WAREHOUSES SET AUTO_SUSPEND = 1", "DROP TABLE USERS",
                "SELECT 1; DELETE FROM USERS", "CREATE TABLE X AS SELECT 1"):
        with pytest.raises(ReadOnlyViolation):
            seeded_tel.query(sql)


def test_findings_are_inferences_and_low_confidence_goes_to_review(seeded_tel):
    store = Store()
    runner = AgentRunner(store, clock=clock)
    runner.run("AG-PIPELINE-TRIAGE", seeded_tel, require_promoted=False)
    inf = store.query("SELECT * FROM ai_inference")
    assert inf and all(r["rationale"] and r["confidence"] is not None for r in inf)
    assert all(r["prompt_template"] == "agents/pipeline_triage@1" for r in inf)
    rubric = default_rubrics().with_overrides({"agents": {"pipeline_triage": {"confidence_cap": 0.98}}})
    # an unknown error text yields a low-confidence inference that lands in the review queue
    from altitude_agents.agents.pipeline_triage import PipelineTriage
    runner2 = AgentRunner(Store(), clock=clock, rubrics=rubric)
    rep = runner2.run("AG-PIPELINE-TRIAGE", seeded_tel, agent=PipelineTriage(signatures=[]), require_promoted=False)
    assert all(f["needs_review"] for f in rep.findings)
    assert runner2.review.open_items("agent_finding")


def test_runs_on_a_sealed_snapshot(snapshot_tel):
    store = Store()
    report = AgentRunner(store, clock=clock).run("AG-RELEASE-CHANGE-WATCHER", snapshot_tel, require_promoted=False)
    assert report.telemetry_ref.startswith("SNAP-")
    assert {f["subject"] for f in report.findings} >= {"BCB-SAMPLE-2026_08-01"}


def test_simulated_executor_rejects_unknown_statements(seeded_tel):
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    for sql in ("DROP DATABASE EDW", "DELETE FROM EDW.SALES.FCT_ORDERS", "ALTER WAREHOUSE NOPE SET AUTO_SUSPEND = 60"):
        with pytest.raises(UnsupportedStatement):
            sim.run(sql)
    assert sim.executed == []


class FakeCursor:
    def __init__(self, con):
        self.con = con
        self.description = None

    def execute(self, sql, params=None):
        self.con.statements.append((sql, params))
        if sql.startswith("SHOW WAREHOUSES"):
            self.description = [("name",), ("size",), ("auto_suspend",), ("max_cluster_count",)]
            self._rows = [("WH_DEVELOPMENT", "Small", 60, 1), ("WH_DEV", "X-Small", 3600, 1)]

    def fetchall(self):
        return self._rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.statements = []

    def cursor(self):
        return FakeCursor(self)


def test_live_executor_renders_for_dbapi(seeded_tel):
    con = FakeConnection()
    live = LiveExecutor(con)
    assert live.current("warehouse", "WH_DEV") == {"warehouse_size": "XSMALL", "auto_suspend": 3600,
                                                  "max_cluster_count": 1}
    from altitude_agents.actions import ActionGateway, ProposedAction
    store = Store()
    gw = ActionGateway(store, load_tenant_policy("default"), clock=clock)
    store.insert("agent_run", {"run_id": "R1", "agent_id": "AG-WAREHOUSE-RIGHTSIZER", "agent_version": "1.0.0",
                               "tenant_id": "default", "trigger": "t", "started_at": clock(), "status": "running"})
    rec = gw.propose("R1", gw.agents["AG-WAREHOUSE-RIGHTSIZER"], ProposedAction(
        "warehouse.set_auto_suspend", "WH_DEV", {"auto_suspend": 60}, "L3", 0.9, "idle"))
    rec = gw.execute(rec.action_id, live, seeded_tel)
    assert con.statements[-1] == ("ALTER WAREHOUSE WH_DEV SET AUTO_SUSPEND = 60", None)
    assert gw.log.latest(rec.action_id)["rollback_payload"].count("AUTO_SUSPEND = 3600") == 1
    dry = LiveExecutor(FakeConnection(), dry_run=True)
    dry.run("ALTER WAREHOUSE WH_DEV SET AUTO_SUSPEND = 60")
    assert dry.executed and not dry.connection.statements


def test_tenant_policy_fallback():
    assert load_tenant_policy("unknown-tenant").tenant_id == "unknown-tenant"
    assert load_tenant_policy("cautious").cap("AG-WAREHOUSE-RIGHTSIZER") == "L2"
