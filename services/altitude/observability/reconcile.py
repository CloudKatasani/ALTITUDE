"""Cost reconciliation: cost KPIs must agree with Snowflake billing (METERING_DAILY_HISTORY credits billed).

Checks, per account and month (``rubric.obs.reconciliation.credits_tolerance_pct``) and per account-day
(``rubric.obs.reconciliation.daily_tolerance_pct``):

- ``warehouse``  KPI-COST-001 (credits billed by warehouse) vs billed WAREHOUSE_METERING credits;
- ``serverless`` KPI-COST-008 (serverless breakdown, from the detailed histories) vs billed non-warehouse credits;
- ``total``      KPI-COST-001 + KPI-COST-008 vs all billed credits;
- ``chargeback`` KPI-COST-003 (cost by cost centre, $) vs KPI-COST-011 (total billed $) — chargeback sums to the bill.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from altitude.core.rubric import RubricSet, default_rubrics

from .db import ObsDatabase

MONTH_TOL_REF = "rubric.obs.reconciliation.credits_tolerance_pct"
DAY_TOL_REF = "rubric.obs.reconciliation.daily_tolerance_pct"


def _diff_pct(kpi: float, billed: float) -> float:
    if billed == 0:
        return 0.0 if kpi == 0 else float("inf")
    return abs(kpi - billed) / abs(billed) * 100.0


def _daily(db: ObsDatabase, sql: str, params: list | None = None) -> dict[tuple[str, date], float]:
    return {(r["ACCOUNT_NAME"], r["DAY"]): float(r["V"] or 0.0) for r in db.query(sql, params)}


def reconcile(db: ObsDatabase, rubrics: RubricSet | None = None, start: date | None = None,
              end: date | None = None) -> dict[str, Any]:
    rubrics = rubrics or default_rubrics()
    month_tol = float(rubrics.get(MONTH_TOL_REF))
    day_tol = float(rubrics.get(DAY_TOL_REF))
    rng = " AND {c} >= ? AND {c} <= ?" if start and end else ""
    p = [start, end] if start and end else []

    billed_wh = _daily(db, "SELECT ACCOUNT_NAME, DAY, sum(CREDITS_BILLED) AS V FROM CURATED.FACT_METERING_DAILY "
                           "WHERE SERVICE_TYPE = 'WAREHOUSE_METERING'" + rng.format(c="DAY") + " GROUP BY 1, 2", p)
    billed_sl = _daily(db, "SELECT ACCOUNT_NAME, DAY, sum(CREDITS_BILLED) AS V FROM CURATED.FACT_METERING_DAILY "
                           "WHERE SERVICE_TYPE <> 'WAREHOUSE_METERING'" + rng.format(c="DAY") + " GROUP BY 1, 2", p)
    kpi_wh = _daily(db, "SELECT ACCOUNT_NAME, PERIOD AS DAY, sum(VALUE) AS V FROM KPI.KPI_COST_001 WHERE TRUE"
                        + rng.format(c="PERIOD") + " GROUP BY 1, 2", p)
    kpi_sl = _daily(db, "SELECT ACCOUNT_NAME, PERIOD AS DAY, sum(VALUE) AS V FROM KPI.KPI_COST_008 WHERE TRUE"
                        + rng.format(c="PERIOD") + " GROUP BY 1, 2", p)
    usd_cc = _daily(db, "SELECT ACCOUNT_NAME, PERIOD AS DAY, sum(VALUE) AS V FROM KPI.KPI_COST_003 WHERE TRUE"
                        + rng.format(c="PERIOD") + " GROUP BY 1, 2", p)
    usd_total = _daily(db, "SELECT ACCOUNT_NAME, PERIOD AS DAY, sum(VALUE) AS V FROM KPI.KPI_COST_011 WHERE TRUE"
                           + rng.format(c="PERIOD") + " GROUP BY 1, 2", p)

    pairs = {
        "warehouse": (kpi_wh, billed_wh),
        "serverless": (kpi_sl, billed_sl),
        "total": ({k: kpi_wh.get(k, 0.0) + kpi_sl.get(k, 0.0) for k in set(kpi_wh) | set(kpi_sl)},
                  {k: billed_wh.get(k, 0.0) + billed_sl.get(k, 0.0) for k in set(billed_wh) | set(billed_sl)}),
        "chargeback": (usd_cc, usd_total),
    }
    days_checked, months = [], []
    ok = True
    for check, (kpi, billed) in pairs.items():
        monthly: dict[tuple[str, date], list[float]] = defaultdict(lambda: [0.0, 0.0])
        for key in sorted(set(kpi) | set(billed)):
            k, b = kpi.get(key, 0.0), billed.get(key, 0.0)
            d = _diff_pct(k, b)
            passed = d <= day_tol
            ok &= passed
            days_checked.append({"check": check, "account": key[0], "day": key[1], "kpi": k, "billed": b,
                                 "diff_pct": d, "ok": passed})
            mk = (key[0], key[1].replace(day=1))
            monthly[mk][0] += k
            monthly[mk][1] += b
        for (acct, m), (k, b) in sorted(monthly.items()):
            d = _diff_pct(k, b)
            passed = d <= month_tol
            ok &= passed
            months.append({"check": check, "account": acct, "month": m, "kpi": round(k, 6), "billed": round(b, 6),
                           "diff_pct": d, "ok": passed})
    return {"ok": ok and bool(months), "tolerance_pct": {"month": month_tol, "day": day_tol},
            "months": months, "days_failed": [d for d in days_checked if not d["ok"]],
            "days_checked": len(days_checked)}
