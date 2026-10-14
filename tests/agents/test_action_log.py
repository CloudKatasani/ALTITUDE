"""The agent-action log (and run/tool-call logs) are append-only and fully reconstructable."""

import pytest

from altitude.core.errors import AppendOnlyViolation
from altitude.core.store import Store
from altitude_agents.actions import ActionLog
from altitude_agents.executor import SimulatedSnowflake
from altitude_agents.runtime import AgentRunner

from .conftest import clock


@pytest.mark.parametrize("sql", [
    "UPDATE agent_action SET status = 'approved'",
    "DELETE FROM agent_action",
    "TRUNCATE agent_action",
    "DROP TABLE agent_action",
    "UPDATE approval SET decision = 'approved'",
    "DELETE FROM agent_run_log",
    "UPDATE agent_tool_call SET rows_returned = 0",
    "DELETE FROM agent_eval_result",
])
def test_logs_reject_mutation(sql):
    with pytest.raises(AppendOnlyViolation):
        Store().execute(sql)


def test_update_api_refuses_action_log():
    s = Store()
    with pytest.raises(AppendOnlyViolation):
        s.update("agent_action", {"action_id": "x"}, {"status": "executed"})
    assert not hasattr(ActionLog, "update") and not hasattr(ActionLog, "delete")


def test_each_transition_is_a_new_row_and_history_is_reconstructable(seeded_tel):
    store = Store()
    runner = AgentRunner(store, clock=clock)
    sim = SimulatedSnowflake(seeded_tel, clock=clock)
    report = runner.run("AG-ACCESS-HYGIENE", seeded_tel, require_promoted=False)
    act = report.action("user.disable", "OLD_ANALYST")
    before = store.scalar("SELECT count(*) FROM agent_action")
    runner.gateway.approve(act.action_id, "alice", approver_role="security-owner")
    runner.gateway.execute(act.action_id, sim)
    assert store.scalar("SELECT count(*) FROM agent_action") == before + 2
    hist = runner.gateway.log.history(act.action_id)
    assert [h["seq"] for h in hist] == [1, 2, 3]
    assert [h["status"] for h in hist] == ["proposed", "approved", "executed"]
    assert [h["actor"] for h in hist] == ["SVC_ALT_ACCESS_HYGIENE", "alice", "alice"]
    # the original proposal row is untouched by later transitions
    assert ActionLog.payload(hist[0])["sql"] == "ALTER USER OLD_ANALYST SET DISABLED = TRUE"
    assert hist[2]["rollback_payload"] and "DISABLED = FALSE" in hist[2]["rollback_payload"]
    # run log: inputs, tool calls, output, decision; approver lives in approval + action rows
    log = store.get("agent_run_log", run_id=report.run_id)
    assert log["decision_summary"] and '"telemetry_ref"' in log["inputs"] and '"findings"' in log["output"]
    calls = store.all("agent_tool_call", order_by="seq", run_id=report.run_id)
    assert [c["tool"] for c in calls] == ["users", "user_role_grants", "role_grants", "roles", "privileged_usage"]
    assert all(c["tables_read"] and c["result_hash"] for c in calls)
    assert store.get("agent_run", run_id=report.run_id)["status"] == "completed"
