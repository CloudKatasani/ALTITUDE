"""Outcome-backed guarantees: fee credit, value floor, re-baseline."""

from __future__ import annotations

from datetime import date

from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics


def catalog() -> dict:
    return load_yaml("commercial/catalog.yaml")


def tier(tier_id: str) -> dict:
    return next(t for t in catalog()["tiers"] if t["tier"] == tier_id)


def qualifies(annual_spend_usd: float, rubrics: RubricSet | None = None) -> bool:
    rubrics = rubrics or default_rubrics()
    return float(annual_spend_usd) >= float(rubrics.get("rubric.commercial.qualification_min_annual_spend_usd"))


def value_floor_credit(tier_id: str, fee_usd: float, identified_p50_usd: float, annual_spend_usd: float,
                       rubrics: RubricSet | None = None) -> dict:
    """If identified annualised opportunity (p50) < multiple x fee, credit the shortfall, capped at the fee."""
    rubrics = rubrics or default_rubrics()
    g = next(x for x in catalog()["guarantees"] if x["id"] == "GUA-VALUE-FLOOR")
    multiple = float(rubrics.get("rubric.commercial.value_floor_multiple"))
    floor = multiple * fee_usd
    if tier_id not in g["applies_to"]:
        return {"eligible": False, "reason": f"value floor applies to {', '.join(g['applies_to'])} only", "credit_usd": 0.0}
    if not qualifies(annual_spend_usd, rubrics):
        return {"eligible": False, "reason": "annual Snowflake spend below the qualification threshold", "credit_usd": 0.0}
    shortfall = max(0.0, floor - identified_p50_usd)
    credit = round(min(fee_usd, shortfall), 2)
    return {"eligible": True, "floor_usd": floor, "identified_p50_usd": identified_p50_usd, "credit_usd": credit,
            "reason": "identified value met the floor" if credit == 0 else "identified value below the floor"}


def fee_credit(tier_id: str, fee_usd: float, diagnostic_end: date, follow_on_signed: date | None,
               prior_credit_for_account: bool = False, rubrics: RubricSet | None = None) -> dict:
    rubrics = rubrics or default_rubrics()
    g = next(x for x in catalog()["guarantees"] if x["id"] == "GUA-FEE-CREDIT")
    window = int(rubrics.get("rubric.commercial.fee_credit_window_days"))
    if tier_id not in g["applies_to"]:
        return {"eligible": False, "credit_usd": 0.0, "reason": f"fee credit applies to {', '.join(g['applies_to'])}"}
    if prior_credit_for_account:
        return {"eligible": False, "credit_usd": 0.0, "reason": "fee credit applies once per account"}
    if follow_on_signed is None or (follow_on_signed - diagnostic_end).days > window:
        return {"eligible": False, "credit_usd": 0.0, "reason": f"no follow-on signed within {window} days"}
    return {"eligible": True, "credit_usd": round(fee_usd, 2), "reason": f"follow-on signed within {window} days"}
