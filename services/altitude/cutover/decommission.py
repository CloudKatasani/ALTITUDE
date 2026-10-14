"""Decommissioning (Section 13.3): block while legacy consumers are active; report realised savings."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from altitude.core.rubric import RubricSet, default_rubrics


def decommission_readiness(store: Any, source_system_id: str, as_of: date, rubrics: RubricSet | None = None) -> dict:
    rubrics = rubrics or default_rubrics()
    window = int(rubrics.get("rubric.cutover.decommission_consumer_window_days"))
    since = as_of - timedelta(days=window)
    active = store.query(
        "SELECT o.fq_name, u.period_end, u.query_count, u.distinct_users FROM usage_stat u "
        "JOIN source_object o ON o.object_id = u.object_id "
        "WHERE o.source_system_id = ? AND u.period_end >= ? AND u.query_count > 0 ORDER BY o.fq_name",
        [source_system_id, since])
    return {"source_system_id": source_system_id, "as_of": as_of.isoformat(), "window_days": window,
            "active_consumers": active, "blocked": bool(active),
            "reason": (f"{len(active)} legacy object(s) still queried in the last {window} days"
                       if active else "no legacy consumers in the window")}


def savings_realisation(legacy_costs: dict[str, float], snowflake_annual_cost: float,
                        decommissioned: bool) -> dict:
    """The number the CFO remembers: legacy run cost removed minus the new platform's run cost."""
    legacy_total = round(sum(legacy_costs.values()), 2)
    realised = round(legacy_total - snowflake_annual_cost, 2) if decommissioned else 0.0
    return {"legacy_annual_cost": legacy_total, "legacy_cost_lines": legacy_costs,
            "snowflake_annual_cost": round(snowflake_annual_cost, 2), "decommissioned": decommissioned,
            "realised_annual_savings": realised,
            "note": "savings are booked only once the legacy platform is off" if not decommissioned else ""}
