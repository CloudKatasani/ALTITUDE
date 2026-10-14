"""M5 acceptance: no artifact is promotable without review; every AI change has confidence, rationale,
model and prompt version. Plus factory transitions, PR packs and the convert_exit gate."""

import json
import re

import pytest

from altitude.conversion import factory
from altitude.conversion.factory import InvalidTransition
from altitude.conversion.remediation import RemediationAgent, apply_rule, assert_not_production, run_pack_tests
from altitude.conversion import kb
from altitude.core.errors import AppendOnlyViolation, ApprovalRequired, ReadOnlyViolation

PROMPT_REF = re.compile(r"^[a-z][a-z0-9_.]*@\d+\.\d+\.\d+$")


def _approve_all(workflow, result, reviewer="lead@partner.example"):
    for c in result.changes:
        workflow.decide_change(c.change_id, reviewer, "approved")


def test_every_ai_change_has_confidence_rationale_model_and_prompt_version(store, converted):
    rows = store.query("SELECT * FROM ai_change")
    assert len(rows) >= 10
    for r in rows:
        assert r["confidence"] is not None and 0 <= float(r["confidence"]) <= 1
        assert r["rationale"] and len(r["rationale"]) > 20
        assert r["model_id"]
        assert all(PROMPT_REF.match(p) for p in r["prompt_template"].split(","))
        assert r["diff"].startswith("--- a/") and r["linked_issue_ids"] and r["tests_generated"]
        assert r["agent_id"] == RemediationAgent.agent_id
        inf = store.get("ai_inference", subject_type="ai_change", subject_id=r["change_id"])
        assert inf and float(inf["confidence"]) == float(r["confidence"]) and inf["prompt_template"] == r["prompt_template"]
    # below-floor changes are queued for human review
    low = store.query("SELECT c.change_id FROM ai_change c JOIN ai_change_patch p USING (change_id) WHERE p.below_floor")
    assert low
    queued = {r["subject_id"] for r in store.query("SELECT subject_id FROM review_item WHERE subject_type='ai_change' AND reason='low_confidence'")}
    assert {r["change_id"] for r in low} <= queued


def test_no_artifact_is_promotable_without_review(store, converted, workflow):
    for target, res in converted.items():
        with pytest.raises(ApprovalRequired):
            workflow.promote(res.artifact_id, "release.manager")
        assert store.get("converted_artifact", artifact_id=res.artifact_id)["promoted_by"] is None


def test_promotion_path_requires_every_gate_condition(store, converted, workflow):
    res = converted["upd_orders.sql"]
    art_id = res.artifact_id
    assert len(res.changes) == 2 and not res.unresolved_issue_ids
    low = [c for c in res.changes if c.below_floor]
    assert [c.rule_ids for c in low] == [["RR-TD-UPDATE-FROM"]]

    # 1. changes undecided -> not promotable; artifact review refused
    with pytest.raises(ApprovalRequired):
        workflow.review_artifact(art_id, "peer@partner.example", "approved")
    gate = workflow.gate(art_id)
    assert not gate.passed and gate.metrics["ai_changes_unreviewed"] == 2
    assert gate.metrics["low_confidence_changes_unreviewed"] == 1

    # 2. anonymous decisions are refused
    with pytest.raises(ApprovalRequired):
        workflow.decide_change(res.changes[0].change_id, "", "approved")

    # 3. all changes decided, but no artifact review -> still not promotable
    _approve_all(workflow, res)
    assert store.scalar("SELECT count(*) FROM review_item WHERE status='open' AND subject_id IN (?, ?)",
                        [c.change_id for c in res.changes]) == 0
    with pytest.raises(ApprovalRequired, match="artifact_review_approved"):
        workflow.promote(art_id, "release.manager")

    # 4. reviewed, but generated tests not run -> not promotable
    workflow.review_artifact(art_id, "peer@partner.example", "approved")
    with pytest.raises(ApprovalRequired, match="unit_test_pass_rate"):
        workflow.promote(art_id, "release.manager")

    # 5. tests pass -> gate passes; promotion needs a named approver and records it
    report = workflow.run_unit_tests(art_id)
    assert report["total"] >= 6 and report["failures"] == {}
    assert workflow.gate(art_id).passed
    with pytest.raises(ApprovalRequired):
        workflow.promote(art_id, " ")
    art = workflow.promote(art_id, "release.manager")
    assert art["status"] == "promoted" and art["promoted_by"] == "release.manager" and art["promoted_at"]
    promoted = store.get("artifact_content", artifact_id=art_id, kind="promoted")["content"]
    assert "UPDATE ord SET status_code = s.status_code FROM stg.order_status s" in promoted
    assert "RESOLVE EWI" not in promoted and "COLLECT STATS" not in promoted

    # factory transitions recorded with actor, evidence and confidence
    hist = factory.history(store, art["object_id"])
    assert [h["to_state"] for h in hist] == ["Converted", "AI-remediated", "Reviewed", "Unit-tested"]
    assert [h["actor_type"] for h in hist] == ["agent", "agent", "human", "system"]
    assert hist[2]["actor"] == "peer@partner.example"
    assert all(h["evidence_ref"] and h["occurred_at"] for h in hist)
    assert float(hist[1]["confidence"]) == min(c.confidence for c in res.changes)
    events = {e["action"] for e in store.query("SELECT action FROM audit_event")}
    assert {"converted_artifact.promoted", "ai_change.approved", "factory.Unit-tested"} <= events


def test_open_p1_blocks_until_fixed_or_accepted(store, converted, workflow):
    res = converted["usp_purge_stage.sql"]
    _approve_all(workflow, res)
    workflow.review_artifact(res.artifact_id, "peer", "approved")
    workflow.run_unit_tests(res.artifact_id)
    gate = workflow.gate(res.artifact_id)
    assert not gate.passed and gate.metrics["open_p1_ewis"] == 1  # the trigger has no automatic fix
    trigger = store.get("conversion_issue", artifact_id=res.artifact_id, code="ALT-EWI-MS0004")
    with pytest.raises(ApprovalRequired):
        workflow.accept_issue(trigger["issue_id"], "architect", "")
    workflow.accept_issue(trigger["issue_id"], "architect", "Audit trigger replaced by stream + task in wave 2 (ADR-014)")
    assert workflow.gate(res.artifact_id).passed
    assert workflow.promote(res.artifact_id, "release.manager")["status"] == "promoted"


def test_rejected_change_is_left_out_and_keeps_issue_open(store, converted, workflow):
    res = converted["upd_orders.sql"]
    update = next(c for c in res.changes if "RR-TD-UPDATE-FROM" in c.rule_ids)
    other = next(c for c in res.changes if c is not update)
    workflow.decide_change(update.change_id, "lead", "rejected", "needs dedupe of stg first")
    workflow.decide_change(other.change_id, "lead", "approved")
    final = workflow.final_content(res.artifact_id)
    assert "UPDATE ord FROM stg.order_status" in final and "COLLECT STATS" not in final
    statuses = {i["code"]: i["status"] for i in store.all("conversion_issue", artifact_id=res.artifact_id)}
    assert statuses == {"ALT-EWI-TD0008": "open", "ALT-EWI-TD0006": "fixed"}
    workflow.review_artifact(res.artifact_id, "peer", "approved")
    report = workflow.run_unit_tests(res.artifact_id)
    assert report["failures"] == {} and report["total"] == len(other.tests)
    assert workflow.gate(res.artifact_id).passed  # the open TD0008 is P2, not blocking


def test_modified_change_is_tested_against_reviewer_text(store, converted, workflow):
    res = converted["upd_orders.sql"]
    update = next(c for c in res.changes if "RR-TD-UPDATE-FROM" in c.rule_ids)
    other = next(c for c in res.changes if c is not update)
    bad = update.after_text.replace("UPDATE ord SET", "UPDATE ord FROM stg.order_status SET")
    workflow.decide_change(update.change_id, "lead", "modified", modified_text=bad)
    workflow.decide_change(other.change_id, "lead", "approved")
    workflow.review_artifact(res.artifact_id, "peer", "approved")
    report = workflow.run_unit_tests(res.artifact_id)
    assert report["failures"]  # reviewer text reintroduced the Teradata construct -> generated test fails
    gate = workflow.gate(res.artifact_id)
    assert not gate.passed and gate.metrics["unit_test_pass_rate"] < 1
    with pytest.raises(ApprovalRequired):
        workflow.promote(res.artifact_id, "release.manager")


def test_pr_pack_contents(converted):
    res = converted["usp_purge_stage.sql"]
    pack = res.pack_dir
    manifest = json.loads((pack / "manifest.json").read_text())
    assert manifest["production"] is False and manifest["_generated"].startswith("AUTO-GENERATED")
    assert set(manifest["changes"]) == {c.change_id for c in res.changes}
    for cid, ch in manifest["changes"].items():
        assert (pack / ch["diff"]).exists() and ch["tests"] and ch["model_id"] and ch["prompt_template"]
    assert {u["code"] for u in manifest["unresolved_issues"]} == {"ALT-EWI-MS0004", "ALT-EWI-MS0003", "ALT-FDM-MS0008"}
    remediated = (pack / "files" / "usp_purge_stage.sql").read_text()
    assert remediated.startswith("-- AUTO-GENERATED")
    assert "LANGUAGE SQL" in remediated and "SQLROWCOUNT" in remediated and "@@ROWCOUNT" not in remediated
    assert "VALUES ('purge_stage', @@ROWCOUNT" in (pack / "original" / "usp_purge_stage.sql").read_text()
    checklist = (pack / "REVIEW_CHECKLIST.md").read_text()
    assert "below review floor" in checklist and "ALT-EWI-MS0004" in checklist
    report = run_pack_tests(pack)
    assert report.total > 0 and report.failures == {}


def test_pr_packs_never_written_to_production(store, tmp_path, monkeypatch):
    prod = tmp_path / "prod"
    prod.mkdir()
    (prod / ".altitude-production").write_text("")
    with pytest.raises(ReadOnlyViolation):
        assert_not_production(prod / "packs" / "PRP-1")
    monkeypatch.setenv("ALTITUDE_PRODUCTION_PATHS", str(tmp_path / "deploy"))
    with pytest.raises(ReadOnlyViolation):
        assert_not_production(tmp_path / "deploy" / "x")
    assert_not_production(tmp_path / "drafts" / "x")


def test_factory_transitions_are_validated_and_append_only(store):
    with pytest.raises(InvalidTransition):
        factory.transition(store, engagement_id="E", object_id="O", to_state="Reviewed", actor="a",
                           actor_type="human", evidence_ref="x", confidence=1)
    factory.transition(store, engagement_id="E", object_id="O", to_state="Converted", actor="a",
                       actor_type="agent", evidence_ref="run:1", confidence=0.7)
    with pytest.raises(InvalidTransition):
        factory.transition(store, engagement_id="E", object_id="O", to_state="Unit-tested", actor="a",
                           actor_type="system", evidence_ref="x", confidence=1)
    with pytest.raises(InvalidTransition):
        factory.transition(store, engagement_id="E", object_id="O", to_state="AI-remediated", actor="a",
                           actor_type="agent", evidence_ref="", confidence=1)
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE factory_transition SET actor='x'")
    with pytest.raises(AppendOnlyViolation):
        store.execute("DELETE FROM factory_transition")


def test_remediation_is_idempotent(store, converted, tmp_path):
    res = converted["upd_orders.sql"]
    again = RemediationAgent(store, packs_root=tmp_path / "other").remediate(res.artifact_id)
    assert again.pack_id == res.pack_id and [c.change_id for c in again.changes] == [c.change_id for c in res.changes]
    assert store.scalar("SELECT count(*) FROM ai_change WHERE artifact_id=?", [res.artifact_id]) == 2


class _FakeLLM:
    name = "anthropic"
    model_id = "claude-opus-5-5"

    def __init__(self):
        self.calls = []

    def complete(self, system, data):
        self.calls.append((system, data))
        return "```sql\nCREATE OR REPLACE VIEW v_orders AS SELECT order_id FROM orders;\n```"


def test_llm_assisted_remediation_for_issues_without_rules(store, tmp_path):
    from altitude.conversion.fallback import SqlglotConverter
    from altitude.conversion.orchestrator import ConversionOrchestrator

    src = tmp_path / "src"
    src.mkdir()
    (src / "trg.sql").write_text("CREATE OR REPLACE TRIGGER t BEFORE INSERT ON orders FOR EACH ROW\nBEGIN\n  NULL;\nEND;\n/\n")
    run = ConversionOrchestrator(store, "E", converter=SqlglotConverter()).run(src, "oracle", tmp_path / "out")
    llm = _FakeLLM()
    res = RemediationAgent(store, packs_root=tmp_path / "packs", provider=llm).remediate(run.artifact_ids[0])
    (change,) = res.changes
    assert change.model_id == "claude-opus-5-5" and change.below_floor
    assert change.prompt_template == kb.prompt_ref("conversion.remediate.freeform")
    system, data = llm.calls[0]
    assert "<untrusted_sql" in data and "CREATE OR REPLACE TRIGGER" not in system
    assert change.after_text.startswith("CREATE OR REPLACE VIEW")
    inf = store.get("ai_inference", subject_id=change.change_id)
    assert inf["provider"] == "anthropic" and inf["needs_review"]


def test_apply_rule_fix_types():
    rules = {r["id"]: r for r in kb.remediation_rules()}
    assert apply_rule(rules["RR-TD-COLLECT-STATS"], "COLLECT STATS ON t COLUMN (a);").startswith("-- removed")
    assert apply_rule(rules["RR-MS-ROWCOUNT"], "SELECT @@ROWCOUNT;") == "SELECT SQLROWCOUNT;"
    assert apply_rule(rules["RR-OR-ROWNUM-LIMIT"], "SELECT a\nFROM t\nWHERE\n  ROWNUM <= 5;") == "SELECT a\nFROM t LIMIT 5;"
    region = "-- !!!RESOLVE EWI!!! x\n-- .LOGON a/b;\n-- .OS rm -rf /tmp/x"
    assert apply_rule(rules["RR-TD-SESSION"], region) == "-- !!!RESOLVE EWI!!! x\n-- .OS rm -rf /tmp/x"
