import hashlib
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from altitude.core.ai import ReviewQueue
from altitude.core.errors import AppendOnlyViolation, ApprovalRequired
from altitude.core.rubric import default_rubrics
from altitude.core.store import Store
from altitude.validation import (Endpoint, Normaliser, TableSpec, ValidationEngine, accept_deviation,
                                 assign_data_owner, generate_suite, render_md, tier_summary)
from altitude.validation.synthetic import CASES

AS_OF = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 12, 0)


def _run(case, store, tmp_path, label="run-1", as_of=AS_OF, rubrics=None, spec_kw=None, **kw):
    spec = case.spec
    if spec_kw:
        spec = TableSpec(**{**spec.__dict__, **spec_kw})
    eng = ValidationEngine(store, case.source, case.target, tmp_path / "mm", rubrics=rubrics)
    return eng.run(generate_suite(spec, rubrics=rubrics), run_label=label, as_of=as_of, now=NOW, **kw)


# ----------------------------------------------------------------------------- suite generation

def test_suite_levels_follow_tier_data():
    spec = TableSpec(object_id="X", source_table="t", key_columns=["id"], queries=[{"id": "Q", "source_sql": "1"}],
                     perf=[{"query_id": "Q", "baseline_p50_ms": 1, "baseline_p95_ms": 1, "target_p50_ms": 1,
                            "target_p95_ms": 1}])
    t1 = generate_suite(spec)
    assert t1.active_levels == ["L0", "L1", "L2", "L3", "L4", "L5"]
    t2 = generate_suite(TableSpec(**{**spec.__dict__, "tier": "tier2"}))
    assert t2.checks_for("L3")[0].mode == "sample"
    assert t2.checks_for("L3")[0].definition["sample_rate_ref"] == "rubric.validation.sampling.l3_sample_rate"
    t3 = generate_suite(TableSpec(**{**spec.__dict__, "tier": "tier3"}))
    assert t3.active_levels == ["L0", "L1", "L2"] and t3.checks_for("L2")[0].mode == "sample"
    assert generate_suite(spec).suite_id == t1.suite_id
    nokey = generate_suite(TableSpec(object_id="X", source_table="t"))
    assert "L3" not in nokey.active_levels
    with pytest.raises(ValueError):
        generate_suite(TableSpec(object_id="X", source_table="t", tier="tier9"))


def test_normalisation_rules_are_versioned_data():
    base, ora = Normaliser(()), Normaliser(("oracle_null_semantics",))
    assert base.version != ora.version and base.version.startswith("norm:1.0.0:")
    assert {r.id for r in ora.applied} - {r.id for r in base.applied} == {"NR-EMPTY-AS-NULL"}
    with pytest.raises(ValueError):
        Normaliser(("no_such_policy",))


# ----------------------------------------------------------------------------- engine behaviour

def test_clean_case_passes_all_levels_and_is_reproducible(tmp_path):
    store = Store()
    case = CASES["clean"]()
    r1 = _run(case, store, tmp_path)
    assert r1.status == "pass" and set(r1.levels) == {"L0", "L1", "L2", "L3", "L4", "L5"}
    r2 = _run(case, store, tmp_path)
    assert {lv: r.run_id for lv, r in r1.levels.items()} == {lv: r.run_id for lv, r in r2.levels.items()}
    assert store.scalar("SELECT count(*) FROM validation_run") == 6
    row = store.get("validation_run", run_id=r1.levels["L3"].run_id)
    assert row["normalisation_rule_version"] == r1.suite.normaliser.version
    assert row["threshold_rubric_version"] == default_rubrics().version
    assert row["executed_in"] == "client_agent"
    case.close()


def test_validation_run_is_append_only(tmp_path):
    store = Store()
    case = CASES["clean"]()
    _run(case, store, tmp_path)
    with pytest.raises(AppendOnlyViolation):
        store.execute("UPDATE validation_run SET result = 'pass'")
    case.close()


def test_runs_store_aggregates_only_and_keys_stay_in_boundary(tmp_path):
    store = Store()
    case = CASES["TD-02"]()
    values = {r[0] for r in case.source.con.execute("SELECT DISTINCT last_name FROM customer").fetchall()}
    values |= {v.upper() for v in values}
    res = _run(case, store, tmp_path)
    for row in store.all("validation_run"):
        text = json.dumps(row["metrics"]) if not isinstance(row["metrics"], str) else row["metrics"]
        assert not any(v in text for v in values), "row values must never reach validation_run"
    ref = res.levels["L3"].mismatch_key_ref
    path, digest = ref[len("file://"):].split("#sha256=")
    body = Path(path).read_text()
    assert hashlib.sha256(body.encode()).hexdigest()[:16] == digest
    lines = [json.loads(x) for x in body.splitlines()]
    assert len(lines) == 4 and all(set(x) == {"key", "category"} for x in lines)
    assert Path(path).parent == (tmp_path / "mm").resolve()
    case.close()


def test_policy_normalisation_neutralises_accepted_drift(tmp_path):
    case = CASES["OR-01"]()
    res = _run(case, Store(), tmp_path, spec_kw={"policies": ["oracle_null_semantics"]})
    assert res.levels["L3"].result == "pass" and res.levels["L2"].result == "pass"
    case.close()
    case = CASES["TD-02"]()
    res = _run(case, Store(), tmp_path, spec_kw={"policies": ["normalise_case"]})
    assert res.status == "pass"
    case.close()


def test_canonical_rendering_ignores_representation_only_differences(tmp_path):
    s, t = duckdb.connect(), duckdb.connect()
    s.execute("CREATE TABLE m (id INTEGER, qty INTEGER, price DECIMAL(10,1), d DATE)")
    s.execute("INSERT INTO m VALUES (1, 5, 1.5, '2026-10-01'), (2, NULL, 2.0, NULL)")
    t.execute("CREATE TABLE m (id BIGINT, qty DECIMAL(12,2), price DECIMAL(12,3), d TIMESTAMP)")
    t.execute("INSERT INTO m VALUES (1, 5.00, 1.500, '2026-10-01 00:00:00'), (2, NULL, 2.000, NULL)")
    spec = TableSpec(object_id="M", source_table="m", key_columns=["id"], source_dialect="oracle")
    res = ValidationEngine(Store(), Endpoint(s), Endpoint(t), tmp_path).run(generate_suite(spec), as_of=AS_OF, now=NOW)
    assert res.status == "pass", {lv: (r.result, r.metrics) for lv, r in res.levels.items()}


def test_rubric_thresholds_drive_results(tmp_path):
    case = CASES["TD-02"]()
    loose = default_rubrics().with_overrides({"validation": {"thresholds": {"tier1": {
        "l3_mismatch_max": 10, "l3_mismatch_rate_max": 0.5}}}})
    res = _run(case, Store(), tmp_path, rubrics=loose)
    assert res.levels["L3"].result == "pass"
    assert res.levels["L3"].metrics["thresholds"]["l3_mismatch_max"] == 10
    case.close()


def test_tier2_samples_keys_deterministically(tmp_path):
    case = CASES["TD-02"]()
    r1 = _run(case, Store(), tmp_path, spec_kw={"tier": "tier2"})
    r2 = _run(case, Store(), tmp_path, spec_kw={"tier": "tier2"})
    m = r1.levels["L3"].metrics
    assert m["sampled"] and 0 < m["keys_compared"] < 30
    assert m == r2.levels["L3"].metrics
    case.close()


def test_tier3_runs_sampled_l2_on_latest_partitions(tmp_path):
    case = CASES["TD-01"]()
    res = _run(case, Store(), tmp_path, spec_kw={"tier": "tier3"})
    assert set(res.levels) == {"L0", "L1", "L2"}
    assert res.levels["L2"].metrics["sampled_partitions"] is True
    # without L3 the L1 failure cannot be attributed and is left for human triage
    assert [c.signature for c in res.levels["L1"].clusters] == ["unexplained"]
    case.close()


def test_l5_performance_parity_uses_supplied_timings(tmp_path):
    case = CASES["clean"]()
    slow = [{"query_id": "KPI-REVENUE", "baseline_p50_ms": 800, "baseline_p95_ms": 2000,
             "target_p50_ms": 900, "target_p95_ms": 4000, "sla_p95_ms": 3000}]
    res = _run(case, Store(), tmp_path, timings=slow)
    l5 = res.levels["L5"]
    assert l5.result == "fail" and l5.metrics["queries"][0]["sla_met"] is False
    assert l5.metrics["queries"][0]["p95_ratio"] == 2.0
    case.close()


def test_low_confidence_clusters_wait_in_review_queue(tmp_path):
    store = Store()
    case = CASES["OR-02"]()
    res = _run(case, store, tmp_path)
    l0 = res.levels["L0"].clusters[0]
    assert l0.confidence < default_rubrics().get("rubric.ai.review_confidence_min")
    queue = ReviewQueue(store)
    assert l0.cluster_id in {i["subject_id"] for i in queue.open_items("mismatch_cluster")}
    assert not queue.is_cleared("mismatch_cluster", l0.cluster_id)
    case.close()


# ----------------------------------------------------------------------------- accepted deviations & summary

def test_accepted_deviation_workflow_and_tier_summary(tmp_path):
    store = Store()
    case = CASES["OR-01"]()
    res = _run(case, store, tmp_path)
    obj = case.spec.object_id
    l3 = res.levels["L3"]
    cluster = l3.clusters[0]
    review_by = AS_OF + timedelta(days=30)

    with pytest.raises(ApprovalRequired):  # no data owner registered yet
        accept_deviation(store, l3.run_id, cluster.cluster_id, "jane@client", review_by, "ok", as_of=AS_OF)
    assign_data_owner(store, obj, "jane@client", "lead@partner")
    with pytest.raises(ApprovalRequired):  # only the data owner may approve
        accept_deviation(store, l3.run_id, cluster.cluster_id, "lead@partner", review_by, "ok", as_of=AS_OF)
    with pytest.raises(ValueError):  # review-by beyond the rubric window
        accept_deviation(store, l3.run_id, cluster.cluster_id, "jane@client", AS_OF + timedelta(days=400), "ok",
                         as_of=AS_OF)
    with pytest.raises(KeyError):
        accept_deviation(store, l3.run_id, "MMC-NOPE", "jane@client", review_by, "ok", as_of=AS_OF)

    summ = tier_summary(store, AS_OF)
    assert summ["overall"] == "not_ready" and summ["tiers"][0]["levels"]["L3"]["fail"] == 1

    dev = accept_deviation(store, l3.run_id, cluster.cluster_id, "jane@client", review_by,
                           "Oracle '' is NULL by design; silver layer applies NULLIF", as_of=AS_OF)
    assert store.get("approval", subject_id=dev)["approver"] == "jane@client"
    assert store.query("SELECT * FROM audit_event WHERE action = 'validation.accept_deviation'")

    summ = tier_summary(store, AS_OF)
    t1 = summ["tiers"][0]
    assert t1["levels"]["L3"] == {"pass": 0, "fail": 0, "accepted_deviation": 1}
    assert t1["levels"]["L2"] == {"pass": 0, "fail": 0, "accepted_deviation": 1}  # same signature scope
    assert t1["outstanding_mismatches"] == 0 and summ["overall"] == "ready"
    assert {d["approver"] for d in t1["accepted_deviations"]} == {"jane@client"}
    md = render_md(summ)
    assert "jane@client" in md and "OR-01" in md

    # a new run before review-by is classified as accepted deviation at run time
    rerun = _run(case, store, tmp_path, label="run-2", as_of=AS_OF + timedelta(days=5))
    assert rerun.levels["L3"].result == "accepted_deviation"
    assert rerun.levels["L3"].metrics["accepted_deviations"] == [dev]
    # ... and fails again once the deviation is past its review-by date
    late = AS_OF + timedelta(days=31)
    rerun = _run(case, store, tmp_path, label="run-3", as_of=late)
    assert rerun.levels["L3"].result == "fail"
    summ = tier_summary(store, late)
    assert summ["overall"] == "not_ready"
    assert any("past review-by" in r for r in summ["tiers"][0]["reasons"])
    case.close()


def test_summary_for_clean_estate_is_ready(tmp_path):
    store = Store()
    case = CASES["clean"]()
    _run(case, store, tmp_path)
    summ = tier_summary(store, AS_OF, engagement_id="ENG-LOCAL")
    assert summ["overall"] == "ready" and summ["tiers"][0]["objects"] == 1
    assert tier_summary(store, AS_OF, engagement_id="OTHER")["tiers"] == []
    case.close()
