"""Every fleet-v1 agent passes its golden incidents; eval results gate promotion; regressions block it."""

import pytest

from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude_agents.agents import AGENTS, CostSentinel
from altitude_agents.errors import AgentNotPromoted, PromotionBlocked
from altitude_agents.evals import load_suite, promote, run_suite
from altitude_agents.runtime import AgentResult, AgentRunner


@pytest.fixture(scope="module")
def reports():
    return {aid: run_suite(aid) for aid in AGENTS}


def test_six_agents_have_suites_and_all_golden_incidents_pass(reports):
    assert set(reports) == {"AG-COST-SENTINEL", "AG-WAREHOUSE-RIGHTSIZER", "AG-PIPELINE-TRIAGE",
                            "AG-ACCESS-HYGIENE", "AG-DQ-INCIDENT", "AG-RELEASE-CHANGE-WATCHER"}
    for aid, rep in reports.items():
        assert len(load_suite(aid)["cases"]) >= 2
        failing = {c.case_id: c.failures for c in rep.cases if not c.passed}
        assert not failing, f"{aid}: {failing}"


def test_promotion_records_versions_and_gates_the_runner(reports, seeded_tel):
    store = Store()
    runner = AgentRunner(store)
    with pytest.raises(AgentNotPromoted):
        runner.run("AG-COST-SENTINEL", seeded_tel)
    for rep in reports.values():
        promote(store, rep, approver="fleet-lead")
    rows = store.query("SELECT agent_id, version, eval_passed FROM agent_version ORDER BY agent_id")
    assert len(rows) == 6 and all(r["eval_passed"] for r in rows)
    assert store.scalar("SELECT count(*) FROM approval WHERE subject_type = 'agent_version'") == 6
    assert runner.run("AG-COST-SENTINEL", seeded_tel).findings


class BrokenSentinel(CostSentinel):
    """A 'prompt change' that silently stops reporting anomalies."""

    version = "1.1.0"

    def run(self, ctx):
        res = super().run(ctx)
        return AgentResult(findings=[f for f in res.findings if f.kind != "anomaly"], summary=res.summary)


def test_deliberately_broken_agent_fails_promotion(reports, seeded_tel):
    store = Store()
    promote(store, reports["AG-COST-SENTINEL"], approver="fleet-lead")       # 1.0.0 good
    broken = run_suite("AG-COST-SENTINEL", agent=BrokenSentinel())
    assert broken.pass_rate < 1.0
    with pytest.raises(PromotionBlocked) as e:
        promote(store, broken, approver="fleet-lead")
    assert "EVAL-COST-001" in str(e.value) and "regressions" in str(e.value)
    assert store.get("agent_version", agent_id="AG-COST-SENTINEL", version="1.1.0")["eval_passed"] is False
    runner = AgentRunner(store)
    with pytest.raises(AgentNotPromoted):
        runner.run("AG-COST-SENTINEL", seeded_tel, agent=BrokenSentinel())
    assert runner.run("AG-COST-SENTINEL", seeded_tel).version == "1.0.0"     # last good version keeps running


def test_regression_blocks_even_when_pass_rate_floor_is_lowered(reports):
    store = Store()
    lenient = default_rubrics().with_overrides({"agents": {"promotion": {"eval_pass_rate_min": 0.5}}})
    promote(store, reports["AG-COST-SENTINEL"], approver="fleet-lead", rubrics=lenient)
    broken = run_suite("AG-COST-SENTINEL", agent=BrokenSentinel())
    assert broken.pass_rate >= 0.5
    with pytest.raises(PromotionBlocked, match="regressions"):
        promote(store, broken, approver="fleet-lead", rubrics=lenient)
