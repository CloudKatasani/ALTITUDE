"""M7: the Well-Architected checker reports findings with remediation playbooks, reproducibly per snapshot."""

import json

import pytest

from altitude.cli import main
from altitude.core.rubric import default_rubrics
from altitude.core.snapshot import Snapshot, SnapshotWriter
from altitude.core.store import Store
from altitude.foundation import wa
from altitude.synthetic.schema import HARVEST_SCHEMA


@pytest.fixture(scope="module")
def seeded_report(seeded_snapshot):
    return wa.run(seeded_snapshot[0])


def test_checks_are_data_in_section_14_9_format():
    checks = wa.load_checks()
    playbooks = wa.load_playbooks()
    assert len(checks) >= 25
    assert {c["section"] for c in checks} == {f"14.{i}" for i in range(1, 9)}
    assert wa.cross_check(checks, playbooks) == []
    example = next(c for c in checks if c["id"] == "WA-COMP-003")
    assert example["threshold_ref"] == "rubric.compute.auto_suspend_max_seconds"
    assert example["remediation"] == {"auto_fix_available": True, "autonomy": "L2", "playbook": "PB-COMP-AUTOSUSPEND"}


def test_seeded_snapshot_findings_carry_playbooks(seeded_report):
    r = seeded_report
    expected = {
        "WA-COMP-003": {"WH_BI_PROD", "WH_BI_ADHOC", "WH_DEV"},
        "WA-IAM-001": {"JSMITH", "TEMP_CONTRACTOR"},
        "WA-IAM-002": {"SVC_FIVETRAN"},
        "WA-NET-003": {"EDW.SALES.DIM_CUSTOMER.EMAIL"},
        "WA-COST-001": {"WH_BI_PROD"},
        "WA-ORG-001": {"EDW"},
        "WA-ENG-001": {"EDW.FINANCE.FCT_REVENUE"},
        "WA-ENG-003": {"JSMITH"},
        "WA-IAM-005": {"ROLE_LEGACY_MKTG"},
        "WA-AI-002": {"sales", "finance"},
        "WA-OPS-001": {"ACME_PROD"},
    }
    for check_id, objects in expected.items():
        f = r.finding(check_id)
        assert f is not None, check_id
        assert objects <= set(f.objects), (check_id, f.objects)
        assert f.playbook["id"] and f.playbook["steps"] and f.rationale
    f = r.finding("WA-COMP-003")
    assert f.threshold == 60 and "WH_ELT_PROD" not in f.objects
    assert "ALTER WAREHOUSE WH_DEV SET AUTO_SUSPEND = 60 AUTO_RESUME = TRUE" in f.remediation_sql
    assert f.playbook["agent"] == {"agent_id": "AG-WAREHOUSE-RIGHTSIZER", "action_type": "warehouse.set_auto_suspend"}
    assert r.rating == "weak" and r.not_applicable == []


def test_clean_snapshot_scores_high(clean_snapshot, seeded_report):
    clean = wa.run(clean_snapshot[0])
    assert clean.overall > seeded_report.overall
    assert clean.rating == "strong"
    for check_id in ("WA-IAM-001", "WA-NET-003", "WA-COST-001", "WA-ORG-001", "WA-OPS-001"):
        assert clean.finding(check_id) is None


def test_reproducible_per_snapshot_and_rubric(seeded_snapshot, seeded_report):
    snap = seeded_snapshot[0]
    again = wa.run(Snapshot.open(snap.path, verify=True))
    assert again.report_hash == seeded_report.report_hash
    assert json.dumps(again.to_dict(), sort_keys=True) == json.dumps(seeded_report.to_dict(), sort_keys=True)
    relaxed = default_rubrics().with_overrides({"compute": {"auto_suspend_max_seconds": 1000}})
    other = wa.run(snap, rubrics=relaxed)
    assert other.rubric_version != seeded_report.rubric_version
    assert set(other.finding("WA-COMP-003").objects) == {"WH_BI_ADHOC", "WH_DEV"}


def test_missing_evidence_tables_are_not_applicable(tmp_path):
    w = SnapshotWriter(tmp_path, "SNAP-PARTIAL", kind="diagnostic", metadata={"window_end": "2026-09-30"})
    for t in ("WAREHOUSES", "USERS", "ACCOUNT_INFO"):
        w.add_table_from_rows(t, [], HARVEST_SCHEMA[t]["columns"])
    r = wa.run(w.seal())
    na = {x["check_id"] for x in r.not_applicable}
    assert "WA-COMP-003" not in na and "WA-ENG-001" in na and "WA-OPS-004" in na
    assert r.findings == []


def test_persist_is_idempotent(seeded_report):
    store = Store()
    assert wa.persist(store, seeded_report) == len(seeded_report.findings)
    assert wa.persist(store, seeded_report) == 0


def test_cli_wa_check_and_markdown(seeded_snapshot, tmp_path, capsys):
    md = tmp_path / "wa.md"
    assert main(["foundation", "wa-check", "--snapshot", str(seeded_snapshot[0].path), "--markdown", str(md)]) == 0
    out = capsys.readouterr().out
    assert "WA-COMP-003" in out and "PB-COMP-AUTOSUSPEND" in out
    text = md.read_text()
    assert "## WA-IAM-001" in text and "PB-IAM-MFA" in text
    assert main(["foundation", "validate"]) == 0
    assert main(["foundation", "terraform", "--out", str(tmp_path / "tf")]) == 0
    assert main(["foundation", "terraform", "--lint", str(tmp_path / "tf"),
                 "--database-regex", "^(DEV|TEST|UAT|PROD)_[A-Z0-9]+_(RAW|CONFORMED|CURATED|SEMANTIC)$"]) == 0
