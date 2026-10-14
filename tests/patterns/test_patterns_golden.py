"""M1 acceptance: each S1 issue has an executable detector and at least one golden test passing on synthetic data."""

import pytest

from altitude.patterns.detectors import REGISTRY, ensure_loaded
from altitude.patterns.golden import coverage_problems, run_case
from altitude.patterns.library import default_library

LIB = default_library()


@pytest.mark.parametrize("test_id", sorted(LIB.tests))
def test_pattern_library_case(test_id):
    res = run_case(LIB.tests[test_id], LIB)
    assert res.checks, "a test case must perform at least one check"
    assert res.passed, "\n".join(f"{c.name}: {c.detail}" for c in res.failures())


def test_library_structure_and_detector_coverage():
    assert coverage_problems(LIB) == []


def test_every_s1_issue_has_detector_and_passing_golden_test():
    ensure_loaded()
    s1 = [i for i in LIB.issues.values() if i.severity == "S1"]
    assert {"TD-01", "TD-02", "TD-03", "TD-04", "TD-05", "TD-08", "TD-11", "OR-01", "OR-02", "OR-03", "OR-08",
            "MS-01", "MS-02", "MS-04", "MS-08", "NZ-04", "NZ-05"} <= {i.id for i in s1}
    for issue in s1:
        assert REGISTRY[issue.detection["detector"]].kind == "static", issue.id
        goldens = [t for t in LIB.tests_for(issue.id) if t["kind"] == "golden"]
        assert goldens, issue.id
        results = [run_case(t, LIB) for t in goldens]
        assert all(r.passed for r in results), issue.id
        names = {c.name for r in results for c in r.checks}
        assert {"naive conversion diverges", "fixed conversion converges",
                "source emulation yields expected rows"} <= names


def test_register_covers_section_10_issue_ids():
    ids = set(LIB.issues)
    assert {f"TD-{n:02d}" for n in range(1, 12)} <= ids
    assert {f"OR-{n:02d}" for n in range(1, 12)} <= ids
    assert {f"MS-{n:02d}" for n in range(1, 11)} <= ids
    assert any(i.startswith("NZ-") for i in ids) and any(i.startswith("RS-") for i in ids)
    for issue in LIB.issues.values():
        assert issue.fix_patterns and issue.last_verified and issue.verified_by


def test_golden_runner_reports_failures():
    """A broken fix must fail the golden test (the runner is not vacuous)."""
    tc = dict(LIB.tests["TC-TD-05-001"])
    tc["fixed"] = {"snowflake": "SELECT SUM(carton_count) / COUNT(*) FROM shipments"}
    res = run_case(tc, LIB)
    assert not res.passed
    assert [c.name for c in res.failures()] == ["fixed conversion converges"]

    tc = dict(LIB.tests["TC-OR-08-001"])
    tc["fixed"] = {"snowflake": "SELECT order_id, UPPER(TO_CHAR(order_dt, 'DD-MON-YY')) FROM orders ORDER BY 1"}
    res = run_case(tc, LIB)  # sqlglot cannot render the format for DuckDB: must fail loudly, not drop it
    assert "fixed conversion converges" in [c.name for c in res.failures()]
