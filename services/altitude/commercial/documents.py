"""SOW and business-case drafts (skills ``draft_sow`` / ``draft_business_case``).

Drafts are documents for human editing: they state every assumption and carry
the rubric version used. Names come from theme tokens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.theme import render

from .guarantees import catalog

_ENV = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), autoescape=False)


def draft_sow(offer_id: str, client: str, tier_id: str | None = None, scope_notes: list[str] | None = None,
              fee_usd: float | None = None, theme: str | None = None) -> str:
    cat = catalog()
    offer = next((o for o in cat["offers"] if o["id"] == offer_id), None)
    if offer is None:
        raise KeyError(f"unknown offer {offer_id}")
    t = next((x for x in cat["tiers"] if x["tier"] == tier_id), None) if tier_id else None
    fee_range = (t or offer)["fee_usd"]
    guarantees = [g for g in cat["guarantees"] if tier_id and tier_id in g["applies_to"]]
    nxt = next((o for o in cat["offers"] if o["id"] == offer.get("next")), None)
    md = _ENV.get_template("sow.md.j2").render(offer=offer, tier=t, client=client, fee=fee_usd, fee_range=fee_range,
                                               guarantees=guarantees, scope_notes=scope_notes or [], next_offer=nxt,
                                               rubric_version=default_rubrics().version)
    return render(md, theme)


def draft_business_case(legacy_annual_costs: dict[str, float], snowflake_annual_cost: float, migration_cost: float,
                        estimate: dict | None = None, rubrics: RubricSet | None = None,
                        theme: str | None = None) -> dict[str, Any]:
    """Simple TCO case: annual savings, NPV over the rubric horizon, payback months; assumptions explicit."""
    rubrics = rubrics or default_rubrics()
    rate = float(rubrics.get("rubric.commercial.business_case.discount_rate"))
    years = int(rubrics.get("rubric.commercial.business_case.horizon_years"))
    legacy = sum(legacy_annual_costs.values())
    saving = legacy - snowflake_annual_cost
    npv = -migration_cost + sum(saving / (1 + rate) ** y for y in range(1, years + 1))
    payback = (migration_cost / saving * 12) if saving > 0 else None
    case = {"legacy_annual_cost": round(legacy, 2), "snowflake_annual_cost": round(snowflake_annual_cost, 2),
            "annual_saving": round(saving, 2), "migration_cost": round(migration_cost, 2), "discount_rate": rate,
            "horizon_years": years, "npv": round(npv, 2), "payback_months": round(payback, 1) if payback else None,
            "estimate": estimate, "rubric_version": rubrics.version,
            "assumptions": [f"legacy cost lines: {', '.join(sorted(legacy_annual_costs))}",
                            "Snowflake cost from the forecast (contract price x modelled credits) — verify with the account team",
                            "migration cost from the p50 estimate unless stated; p80 shown for risk",
                            f"discount rate {rate:.0%} over {years} years (rubric)"]}
    case["markdown"] = render(_ENV.get_template("business_case.md.j2").render(case=case), theme)
    return case
