from datetime import date

import pytest

from altitude.benchmark import ConsentRequired, contribute, position
from altitude.core.store import Store
from altitude.gtm import record_signal, score_accounts


def test_benchmark_requires_consent_and_minimum_cohort():
    s = Store()
    with pytest.raises(ConsentRequired):
        contribute(s, "t0", None, "utilities", "1-5M", "2026-Q3", {"KPI-COST-007": 0.3})
    for i, v in enumerate([0.10, 0.20, 0.30, 0.40]):
        contribute(s, f"t{i}", "MSA-7.2", "utilities", "1-5M", "2026-Q3", {"KPI-COST-007": v})
    assert position(s, "KPI-COST-007", 0.55, "utilities")["published"] is False
    contribute(s, "t9", "MSA-7.2", "utilities", "1-5M", "2026-Q3", {"KPI-COST-007": 0.50})
    p = position(s, "KPI-COST-007", 0.55, "utilities")
    assert p["published"] and p["cohort_size"] == 5 and p["quartile"] == 4 and p["label"] == "worst quartile"
    assert position(s, "KPI-COST-007", 0.05, "utilities")["quartile"] == 1
    rows = s.query("SELECT DISTINCT contributor_hash FROM benchmark_observation")
    assert all(not r["contributor_hash"].startswith("t") for r in rows)  # tenant ids never stored


def test_buying_signals_scored_and_matched_to_plays():
    s = Store()
    record_signal(s, "Grid Co", "renewal_window", date(2026, 10, 1), "crm", "2028-03-31")
    record_signal(s, "Grid Co", "job_posting", date(2026, 9, 1), "jobs", "Teradata migration lead")
    record_signal(s, "Water Co", "cost_overrun_news", date(2026, 9, 1), "news", "Snowflake bill 2x forecast")
    ranked = score_accounts(s, date(2026, 10, 14), {"Water Co": {"snowflake_customer": True, "regulated_industry": True}})
    assert [r["account"] for r in ranked] == ["Grid Co", "Water Co"]
    grid, water = ranked
    assert grid["offer"] == "OFF-ASSESS" and grid["priority"] == "warm" and grid["score"] == 50
    assert water["offer"] == "OFF-D0" and water["play"] == "PLAY-01"
