"""M11 acceptance: the EAIRN readiness score is reproducible per snapshot."""

import json

import pytest

from altitude.airready import scoring
from altitude.cli import main
from altitude.core.errors import KnowledgeValidationError
from altitude.core.rubric import default_rubrics
from altitude.core.snapshot import Snapshot, SnapshotWriter
from altitude.core.store import Store
from altitude.synthetic.schema import HARVEST_SCHEMA


@pytest.fixture(scope="module")
def seeded(seeded_snapshot):
    return scoring.score(seeded_snapshot[0])


@pytest.fixture(scope="module")
def clean(clean_snapshot):
    return scoring.score(clean_snapshot[0])


def test_eight_pillars_scored_from_snapshot_checks(seeded):
    assert set(seeded.pillars) == set(scoring.PILLARS) and len(scoring.PILLARS) == 8
    assert all(v["checks"] >= 3 for v in seeded.pillars.values())
    assert seeded.snapshot_id == "SNAP-ACME-2026-09-30-SEEDED"
    assert seeded.rubric_version.startswith("rubric:") and seeded.checks_version and seeded.registry_version


def test_readiness_score_is_reproducible_per_snapshot(seeded_snapshot, seeded):
    snap = seeded_snapshot[0]
    again = scoring.score(snap)
    reopened = scoring.score(Snapshot.open(snap.path, verify=True))
    assert again.score_hash == reopened.score_hash == seeded.score_hash
    assert json.dumps(reopened.to_dict(), sort_keys=True) == json.dumps(seeded.to_dict(), sort_keys=True)
    store = Store()
    assert scoring.persist(store, seeded) is True
    assert scoring.persist(store, reopened) is False                 # same inputs => same row, nothing new
    row = store.get("airready_score", snapshot_id=seeded.snapshot_id)
    assert row["score_hash"] == seeded.score_hash and float(row["overall"]) == seeded.overall


def test_persist_detects_irreproducible_rescore(seeded):
    store = Store()
    scoring.persist(store, seeded)
    import copy
    tampered = copy.deepcopy(seeded)
    tampered.overall = seeded.overall + 1
    with pytest.raises(KnowledgeValidationError, match="not reproducible"):
        scoring.persist(store, tampered)


def test_score_reflects_the_estate(seeded, clean):
    assert clean.overall > seeded.overall
    assert clean.maturity_level > seeded.maturity_level
    assert seeded.check("AIR-SEC-001").gaps == ["EDW.SALES.DIM_CUSTOMER.EMAIL"]
    assert seeded.check("AIR-SEM-001").score == 0.0 and set(seeded.check("AIR-SEM-001").gaps) == {"sales", "finance"}
    assert seeded.check("AIR-SEM-002").gaps == ["revenue"]            # two definitions of Revenue in BI
    assert seeded.check("AIR-AIE-002").gaps == ["FR_ANALYST"]
    assert clean.check("AIR-SEM-002").score == 1.0 and clean.check("AIR-SEC-001").passed
    assert seeded.check("AIR-SEM-003").score is None                 # no semantic views => not applicable
    assert seeded.priorities and all(p["playbook"].startswith("PB-") for p in seeded.priorities)


def test_rubric_change_is_a_new_versioned_score(seeded_snapshot, seeded):
    weighted = default_rubrics().with_overrides({"airready": {"pillar_weights": {"semantic_layer": 5.0}}})
    other = scoring.score(seeded_snapshot[0], rubrics=weighted)
    assert other.rubric_version != seeded.rubric_version
    assert other.overall < seeded.overall and other.score_hash != seeded.score_hash


def test_different_snapshot_different_score(clean, seeded):
    assert clean.snapshot_hash != seeded.snapshot_hash and clean.score_hash != seeded.score_hash


def test_missing_tables_are_not_applicable(tmp_path):
    w = SnapshotWriter(tmp_path, "SNAP-MIN", kind="diagnostic", metadata={"window_end": "2026-09-30"})
    w.add_table_from_rows("ACCOUNT_INFO", [{"ACCOUNT_NAME": "X", "NETWORK_POLICY": "NP"}],
                          HARVEST_SCHEMA["ACCOUNT_INFO"]["columns"])
    r = scoring.score(w.seal())
    assert r.check("AIR-SEC-004").score == 1.0
    assert r.check("AIR-DQ-001").score is None and r.pillars["data_quality"]["score"] is None
    assert r.overall == 100.0


def test_cli_score(seeded_snapshot, tmp_path, capsys):
    md = tmp_path / "air.md"
    assert main(["airready", "score", "--snapshot", str(seeded_snapshot[0].path), "--markdown", str(md),
                 "--store", str(tmp_path / "s.duckdb")]) == 0
    out = capsys.readouterr().out
    assert "EAIRN" in out and "semantic_layer" in out and "PB-AI-SEMANTIC-VIEWS" in out
    assert "| semantic_layer |" in md.read_text()
