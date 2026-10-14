import os

import pytest

from altitude.core.errors import AppendOnlyViolation
from altitude.core.snapshot import Snapshot, SnapshotWriter
from altitude.core.store import Store


def test_canonical_model_tables_exist():
    s = Store()
    tables = set(s.tables())
    for t in ["tenant", "engagement", "source_object", "known_issue", "ai_change", "validation_run", "snapshot",
              "audit_event", "agent_action", "approval", "estimate", "wave", "converted_artifact", "review_item"]:
        assert t in tables


@pytest.mark.parametrize("sql", [
    "UPDATE audit_event SET actor = 'x'",
    "DELETE FROM snapshot",
    "delete from main.approval where 1=1",
    "TRUNCATE audit_event",
    "DROP TABLE gate",
    "ALTER TABLE validation_run ADD COLUMN x INT",
    "UPDATE agent_action SET status = 'executed'",
])
def test_append_only_kill_test(sql):
    s = Store()
    with pytest.raises(AppendOnlyViolation):
        s.execute(sql)


def test_update_api_refuses_append_only():
    s = Store()
    with pytest.raises(AppendOnlyViolation):
        s.update("snapshot", {"snapshot_id": "x"}, {"kind": "y"})
    s.insert("tenant", {"tenant_id": "t1", "name": "Acme", "created_at": "2026-01-01"})
    s.update("tenant", {"tenant_id": "t1"}, {"name": "Acme Corp"})
    assert s.get("tenant", tenant_id="t1")["name"] == "Acme Corp"


def test_snapshot_is_sealed_and_verifiable(tmp_path):
    w = SnapshotWriter(tmp_path, "SNAP-T-1", kind="diagnostic", metadata={"tenant_id": "t1"})
    w.add_table_from_rows("T", [{"A": 1, "B": "x"}, {"A": 2, "B": "y"}], {"A": "INTEGER", "B": "VARCHAR"})
    snap = w.seal()
    assert snap.tables() == ["T"]
    snap.verify()
    with pytest.raises(AppendOnlyViolation):
        w.add_table_from_rows("U", [], {"A": "INTEGER"})
    with pytest.raises(AppendOnlyViolation):
        SnapshotWriter(tmp_path, "SNAP-T-1", kind="diagnostic")
    assert not os.access(snap.path, os.W_OK) or os.geteuid() == 0
    with pytest.raises(Exception):
        snap.con.execute("INSERT INTO T VALUES (3, 'z')")
    s = Store()
    snap.register(s)
    assert s.get("snapshot", snapshot_id="SNAP-T-1")["content_hash"] == snap.content_hash
    again = Snapshot.open(snap.path, verify=True)
    assert again.content_hash == snap.content_hash
