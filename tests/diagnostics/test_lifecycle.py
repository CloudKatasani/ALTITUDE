"""Persistence (migration 0100) and the suggestion lifecycle with the review queue."""

import pytest
import sqlglot

from altitude.core.errors import AppendOnlyViolation, ApprovalRequired
from altitude.core.paths import repo_root
from altitude.core.store import Store
from altitude.diagnostics import lifecycle


@pytest.fixture
def store(seeded_result):
    s = Store()
    lifecycle.persist(seeded_result, s)
    return s


def test_migration_is_postgres_and_transpiles_to_duckdb():
    path = repo_root() / "services/altitude/core/migrations/0100_diagnostics.sql"
    text = path.read_text()
    assert sqlglot.parse(text, read="postgres")
    assert all(s.strip() for s in sqlglot.transpile(text, read="postgres", write="duckdb"))
    tables = set(Store().tables())
    assert {"diag_run", "diag_evidence", "diag_suggestion", "diag_suggestion_event", "diag_score"} <= tables


def test_persist_is_idempotent_and_complete(seeded_result, store):
    n = len(seeded_result.suggestions)
    assert store.scalar("SELECT count(*) FROM diag_suggestion") == n
    assert store.scalar("SELECT count(*) FROM diag_evidence") == len(seeded_result.evidence)
    assert store.scalar("SELECT count(*) FROM ai_inference WHERE subject_type = 'suggestion'") == n
    assert store.scalar("SELECT count(*) FROM diag_score WHERE scope = 'domain'") == 10
    lifecycle.persist(seeded_result, store)
    assert store.scalar("SELECT count(*) FROM diag_suggestion") == n
    assert store.scalar("SELECT count(*) FROM diag_run") == 1


def test_low_confidence_suggestions_are_queued_and_need_a_reviewer(seeded_result, store):
    low = [d for d in seeded_result.details if d.needs_review]
    assert low
    queued = {i["subject_id"]: i["reason"] for i in store.query("SELECT * FROM review_item WHERE status = 'open'")}
    for d in low:
        assert queued[d.id] == "low_confidence"
    sid = low[0].id
    with pytest.raises(ApprovalRequired):
        lifecycle.accept(store, sid, reviewer=None)
    with pytest.raises(ApprovalRequired):
        lifecycle.accept(store, sid, reviewer="lead@client")       # still in the review queue
    with pytest.raises(ApprovalRequired):
        lifecycle.review(store, sid, reviewer="", decision="approved")
    lifecycle.review(store, sid, reviewer="lead@client", decision="approved", comment="validated in workshop")
    row = lifecycle.accept(store, sid, reviewer="lead@client")
    assert row["status"] == "accepted" and row["reviewer"] == "lead@client"
    assert lifecycle.statuses(store)[0]["status"] in {"proposed", "accepted"}


def test_full_lifecycle_and_history(seeded_result, store):
    d = next(x for x in seeded_result.details if not x.needs_review and x.review_reason is None)
    sid = d.id
    with pytest.raises(ApprovalRequired):
        lifecycle.transition(store, sid, "accepted", actor="someone")    # no named reviewer
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.transition(store, sid, "value_realised", actor="x", reviewer="y")
    lifecycle.accept(store, sid, reviewer="platform-owner@client")
    lifecycle.transition(store, sid, "implemented", actor="engineer@client", comment="PR #12 merged")
    row = lifecycle.transition(store, sid, "value_realised", actor="package-o", comment="KPI-COST-007 down 40%")
    assert row["status"] == "value_realised" and row["reviewer"] == "platform-owner@client"
    hist = [h["to_status"] for h in lifecycle.history(store, sid)]
    assert hist == ["proposed", "accepted", "implemented", "value_realised"]
    with pytest.raises(lifecycle.LifecycleError):
        lifecycle.reject(store, sid, reviewer="x")
    recs = lifecycle.overlay_status(seeded_result, store)
    assert next(r for r in recs if r["id"] == sid)["status"] == "value_realised"
    assert store.query("SELECT * FROM audit_event WHERE subject_id = ?", [sid])


def test_reject_records_reviewer_and_events_are_append_only(seeded_result, store):
    sid = next(x for x in seeded_result.details if x.review_reason is None).id
    with pytest.raises(ApprovalRequired):
        lifecycle.reject(store, sid, reviewer=None)
    row = lifecycle.reject(store, sid, reviewer="lead@client", comment="false positive: planned decommission")
    assert row["status"] == "rejected" and row["reviewer"] == "lead@client"
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE diag_suggestion_event SET actor = 'x'")
    with pytest.raises(AppendOnlyViolation):
        store.execute("DELETE FROM diag_evidence")
