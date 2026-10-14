from datetime import date

from altitude.commercial import draft_business_case, draft_sow, fee_credit, value_floor_credit


def test_value_floor_credit_rules():
    c = value_floor_credit("D2", 60000, identified_p50_usd=120000, annual_spend_usd=1_000_000)
    assert c["eligible"] and c["credit_usd"] == 60000  # floor 180k, shortfall 60k, cap = fee 60k
    assert value_floor_credit("D2", 60000, 500000, 1_000_000)["credit_usd"] == 0
    assert value_floor_credit("D2", 60000, 0, 1_000_000)["credit_usd"] == 60000  # capped at the fee
    assert not value_floor_credit("D1", 25000, 0, 1_000_000)["eligible"]
    assert not value_floor_credit("D2", 60000, 0, 50_000)["eligible"]  # below qualification threshold


def test_fee_credit_window_and_once_per_account():
    assert fee_credit("D2", 60000, date(2026, 10, 1), date(2026, 11, 15))["credit_usd"] == 60000
    assert not fee_credit("D2", 60000, date(2026, 10, 1), date(2027, 1, 15))["eligible"]
    assert not fee_credit("D2", 60000, date(2026, 10, 1), date(2026, 10, 2), prior_credit_for_account=True)["eligible"]
    assert not fee_credit("D3", 90000, date(2026, 10, 1), date(2026, 10, 2))["eligible"]


def test_sow_and_business_case_drafts():
    sow = draft_sow("OFF-D", "Acme Utilities", tier_id="D2", scope_notes=["Power BI as the BI tool"])
    assert "Value floor" in sow and "Fee credit" in sow and "{{" not in sow and "Acme Utilities" in sow
    partner = draft_sow("OFF-D", "Acme", tier_id="D2", theme="partner_example")
    assert "Example Consulting LLP" in partner and "ALTITUDE" not in partner
    case = draft_business_case({"licence": 900000, "hardware": 300000}, 450000, 600000)
    assert case["annual_saving"] == 750000 and case["payback_months"] == 9.6 and case["npv"] > 0
    assert "Payback" in case["markdown"]
