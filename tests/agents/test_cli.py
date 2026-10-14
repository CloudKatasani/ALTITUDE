import re

from altitude.cli import main


def test_agents_cli_run_approve_execute_log(seeded_snapshot, tmp_path, capsys):
    snap, _ = seeded_snapshot
    store = str(tmp_path / "cp.duckdb")
    assert main(["agents", "list"]) == 0
    assert "AG-SEMANTIC-STEWARD" in capsys.readouterr().out
    assert main(["agents", "run", "AG-ACCESS-HYGIENE", "--snapshot", str(snap.path), "--store", store,
                 "--allow-unpromoted"]) == 0
    out = capsys.readouterr().out
    action_id = re.search(r"action\s+(ACT-\w+) L2 proposed\s+user\.disable\s+OLD_ANALYST", out).group(1)
    assert main(["agents", "approve", action_id, "--approver", "alice", "--role", "security-owner",
                 "--store", store]) == 0
    assert main(["agents", "execute", action_id, "--snapshot", str(snap.path), "--store", store, "--simulate"]) == 0
    assert "ALTER USER OLD_ANALYST SET DISABLED = TRUE" in capsys.readouterr().out
    assert main(["agents", "log", action_id, "--store", store]) == 0
    assert [ln.split()[3] for ln in capsys.readouterr().out.strip().splitlines()] == ["proposed", "approved", "executed"]


def test_agents_cli_refuses_unpromoted_and_promotes_after_evals(seeded_snapshot, tmp_path, capsys):
    snap, _ = seeded_snapshot
    store = str(tmp_path / "cp.duckdb")
    import pytest

    from altitude_agents.errors import AgentNotPromoted
    with pytest.raises(AgentNotPromoted):
        main(["agents", "run", "AG-RELEASE-CHANGE-WATCHER", "--snapshot", str(snap.path), "--store", store])
    assert main(["agents", "evals", "--agent", "AG-RELEASE-CHANGE-WATCHER", "--promote", "--approver", "lead",
                 "--store", store]) == 0
    assert main(["agents", "run", "AG-RELEASE-CHANGE-WATCHER", "--snapshot", str(snap.path), "--store", store]) == 0
    assert "BCB-SAMPLE-2026_08-01" in capsys.readouterr().out
