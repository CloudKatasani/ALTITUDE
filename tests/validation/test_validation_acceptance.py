"""M6 acceptance: synthetic drift cases TD-01, TD-02, OR-01, MS-01 are detected and correctly clustered."""

import json
from datetime import date, datetime

import pytest

from altitude.core.store import Store
from altitude.validation import ValidationEngine, generate_suite
from altitude.validation.synthetic import CASES

AS_OF = date(2026, 10, 14)
NOW = datetime(2026, 10, 14, 12, 0)


def run_case(name, tmp_path, store=None, **kw):
    case = CASES[name]()
    store = store or Store()
    try:
        res = ValidationEngine(store, case.source, case.target, tmp_path / "mismatch").run(
            generate_suite(case.spec), as_of=AS_OF, now=NOW, **kw)
    finally:
        case.close()
    return case, store, res


@pytest.mark.parametrize("name, signature, failing_levels", [
    ("TD-01", "duplicate_rows", {"L1", "L2", "L3"}),
    ("TD-02", "case_only", {"L2", "L3"}),
    ("OR-01", "empty_vs_null", {"L2", "L3"}),
    ("MS-01", "case_only", {"L2", "L3", "L4"}),
])
def test_acceptance_drift_detected_and_clustered_to_known_issue(name, signature, failing_levels, tmp_path):
    case, store, res = run_case(name, tmp_path)
    # detected
    assert res.status == "fail"
    assert {lv for lv, r in res.levels.items() if r.result == "fail"} == failing_levels
    # clustered to the right known issue, and to nothing else
    l3 = res.levels["L3"].clusters
    assert [(c.signature, c.known_issue_id) for c in l3] == [(signature, name)]
    assert {c.known_issue_id for c in res.clusters} == {name}
    assert all(c.fix_pattern_id and c.fix_pattern_id.startswith(f"FX-{name}-") for c in res.clusters)
    # persisted with confidence + rationale, linked to the AI inference record
    rows = store.query("SELECT * FROM mismatch_cluster WHERE known_issue_id = ?", [name])
    assert rows and all(r["rationale"] and float(r["confidence"]) > 0 for r in rows)
    inf = store.query("SELECT * FROM ai_inference WHERE subject_type = 'mismatch_cluster'")
    assert inf and all(json.loads(i["output"])["known_issue_id"] == name for i in inf)
    assert all(i["prompt_template"] == "validation.mismatch_triage@1.0.0" and i["rationale"] for i in inf)


def test_md01_l4_kpi_diff_clustered_by_reaggregation(tmp_path):
    _, _, res = run_case("MS-01", tmp_path)
    l4 = res.levels["L4"]
    assert l4.metrics["queries"][0]["diff_rows"] > 0
    assert [(c.signature, c.column, c.known_issue_id) for c in l4.clusters] == [
        ("case_only", "KPI-CUSTOMERS-BY-STATUS", "MS-01")]


def test_td01_count_delta_is_attributed_to_duplicates(tmp_path):
    _, _, res = run_case("TD-01", tmp_path)
    l1 = res.levels["L1"]
    assert l1.metrics["delta"] == 3 and l1.metrics["partitions_mismatched"] == 3
    assert [(c.signature, c.known_issue_id, c.count) for c in l1.clusters] == [("duplicate_rows", "TD-01", 3)]
    assert res.levels["L3"].metrics["by_category"] == {"duplicate_rows": 3}


@pytest.mark.parametrize("name, signature", [
    ("TD-03", "trailing_space"), ("OR-02", "scale_truncation"), ("OR-03", "time_component_lost"),
    ("MS-02", "timestamp_precision"),
])
def test_further_drift_signatures(name, signature, tmp_path):
    _, _, res = run_case(name, tmp_path)
    assert [(c.signature, c.known_issue_id) for c in res.levels["L3"].clusters] == [(signature, name)]


def test_schema_level_drift_is_clustered(tmp_path):
    _, _, res = run_case("OR-02", tmp_path)
    l0 = res.levels["L0"]
    assert l0.result == "fail"
    assert l0.metrics["type_mismatches"] == [{"column": "amount", "source_type": "DECIMAL(12,2)",
                                              "target_type": "DECIMAL(12,0)", "problem": "scale_reduced"}]
    assert [(c.signature, c.known_issue_id) for c in l0.clusters] == [("scale_truncation", "OR-02")]
