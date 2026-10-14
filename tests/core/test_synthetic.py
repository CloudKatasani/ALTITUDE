from altitude.synthetic import AccountSpec, generate
from altitude.synthetic.snowflake_account import ALL_ISSUES, score_detection


def test_seeded_profile_covers_catalogue_and_is_deterministic():
    a = generate()
    checks = {x["check_id"] for x in a.seeded}
    assert checks == set(ALL_ISSUES)
    b = generate()
    assert a.tables["QUERY_HISTORY"][:50] == b.tables["QUERY_HISTORY"][:50]


def test_clean_profile_has_no_seeded_issues():
    assert generate(AccountSpec(profile="clean")).seeded == []


def test_overlapping_windows_share_identical_rows():
    from datetime import date
    a = generate(AccountSpec(end_date=date(2026, 9, 30), days=10))
    b = generate(AccountSpec(end_date=date(2026, 10, 5), days=10))
    day = date(2026, 9, 28)
    ra = [r for r in a.tables["WAREHOUSE_METERING_HISTORY"] if r["START_TIME"].date() == day]
    rb = [r for r in b.tables["WAREHOUSE_METERING_HISTORY"] if r["START_TIME"].date() == day]
    assert ra and ra == rb


def test_score_detection():
    a = generate()
    perfect = [{"check_id": x["check_id"], "affected_objects": [x["object"]]} for x in a.seeded]
    s = score_detection(perfect, a)
    assert s["recall"] == 1.0 and s["false_positive_rate"] == 0.0
    bad = perfect + [{"check_id": "DX-COST-01", "affected_objects": ["WH_ELT_PROD"]}]
    assert score_detection(bad, a)["false_positives"]
