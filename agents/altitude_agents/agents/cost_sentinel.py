"""Cost Sentinel (Section 18.2 #1, max L1): credit anomalies vs a forecast band, month-end forecast,
spike explanation by query signature and user. Read-only; outputs are findings and recommendations."""

from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, timedelta

from ..runtime import AgentContext, AgentResult, BaseAgent, Finding


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5  # threshold-ok: ISO weekday index of Saturday, not a tunable


def _stats(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    mean = sum(values) / len(values)
    var = sum((v - mean) ** 2 for v in values) / len(values)
    return mean, math.sqrt(var)


class CostSentinel(BaseAgent):
    agent_id = "AG-COST-SENTINEL"
    version = "1.0.0"

    def run(self, ctx: AgentContext) -> AgentResult:
        base_days = int(ctx.r("cost_sentinel.baseline_days"))
        eval_days = int(ctx.r("cost_sentinel.evaluation_days"))
        min_hist = int(ctx.r("cost_sentinel.min_history_days"))
        sigma = float(ctx.r("cost_sentinel.band_sigma"))
        min_inc = float(ctx.r("cost_sentinel.min_increase_pct"))
        floor = float(ctx.r("cost_sentinel.min_daily_credits"))
        today = ctx.as_of.date()

        series: dict[str, dict[date, float]] = defaultdict(dict)
        for r in ctx.call("warehouse_daily_credits", days=base_days + eval_days):
            series[r["WAREHOUSE_NAME"]][r["DAY"]] = float(r["CREDITS"])
        account = {r["DAY"]: float(r["CREDITS"]) for r in ctx.call("daily_credits", days=base_days + eval_days)}
        if account:
            series["ACCOUNT"] = account
        first_day = min((d for s in series.values() for d in s), default=today)

        findings: list[Finding] = []
        for name in sorted(series):
            s = series[name]
            for offset in range(eval_days - 1, -1, -1):
                d = today - timedelta(days=offset)
                window = [d - timedelta(days=i) for i in range(1, base_days + 1)]
                if (d - first_day).days < min_hist:
                    continue
                same = [s.get(x, 0.0) for x in window if x >= first_day and _is_weekend(x) == _is_weekend(d)]
                mean, std = _stats(same)
                value = s.get(d, 0.0)
                if value < floor:
                    continue
                upper = mean + sigma * std
                if value <= upper or value <= mean * (1 + min_inc):
                    continue
                z = (value - mean) / std if std else sigma + 1
                conf = min(float(ctx.r("cost_sentinel.confidence_cap")),
                           float(ctx.r("cost_sentinel.confidence_base"))
                           + float(ctx.r("cost_sentinel.confidence_per_sigma")) * max(z - sigma, 0.0))
                detail = {"day": d.isoformat(), "credits": round(value, 4), "baseline_mean": round(mean, 4),
                          "band_upper": round(upper, 4), "z": round(z, 2), "increase_pct": round(value / mean - 1, 4)
                          if mean else None}
                drivers = self._explain(ctx, name, d, base_days) if name != "ACCOUNT" else []
                detail["top_contributors"] = drivers
                driver_txt = "; ".join(f"{x['signature']} by {x['user']} +{x['delta_credits']:.2f} cr"
                                       for x in drivers) or "no attributable query signature"
                findings.append(Finding(
                    kind="anomaly", subject=name,
                    title=f"{name}: {value:.1f} credits on {d} vs band <= {upper:.1f} (mean {mean:.1f})",
                    confidence=round(conf, 3),
                    rationale=(f"{name} credits exceeded the {sigma}-sigma band of the trailing {len(same)} "
                               f"comparable days by {value - upper:.1f}; drivers: {driver_txt}"),
                    detail=detail, evidence=[f"WAREHOUSE_METERING_HISTORY:{name}:{d}"],
                    recommendation=(f"Investigate {drivers[0]['signature']} ({drivers[0]['user']}) on {name}: "
                                    f"+{drivers[0]['delta_credits']:.2f} credits vs baseline on {d}"
                                    if drivers else f"Review {name} usage on {d} before the invoice closes")))
        findings.extend(self._forecast(ctx, account, base_days, min_hist))
        n = sum(1 for f in findings if f.kind == "anomaly")
        return AgentResult(findings=findings, summary=f"{n} credit anomal{'y' if n == 1 else 'ies'}; month-end forecast")

    def _explain(self, ctx: AgentContext, warehouse: str, d: date, base_days: int) -> list[dict]:
        per: dict[tuple[str, str], dict[date, float]] = defaultdict(dict)
        for r in ctx.call("signature_credits", warehouse=warehouse, day=d.isoformat(), baseline_days=base_days):
            per[(r["SIG"], r["USER_NAME"])][r["DAY"]] = float(r["CREDITS"])
        rows = []
        for (sig, user), days in per.items():
            same = [v for x, v in days.items() if x < d and _is_weekend(x) == _is_weekend(d)]
            baseline_days = [x for x in (d - timedelta(days=i) for i in range(1, base_days + 1))
                             if _is_weekend(x) == _is_weekend(d)]
            mean = sum(same) / len(baseline_days) if baseline_days else 0.0
            delta = days.get(d, 0.0) - mean
            if delta > 0:
                rows.append({"signature": sig, "user": user, "credits": round(days.get(d, 0.0), 4),
                             "baseline": round(mean, 4), "delta_credits": round(delta, 4)})
        rows.sort(key=lambda x: (-x["delta_credits"], x["signature"], x["user"]))
        return rows[: int(ctx.r("cost_sentinel.top_contributors"))]

    def _forecast(self, ctx: AgentContext, account: dict[date, float], base_days: int, min_hist: int) -> list[Finding]:
        if not account:
            return []
        today = ctx.as_of.date()
        target = today + timedelta(days=1)
        month_start = target.replace(day=1)
        month_end = target.replace(day=calendar.monthrange(target.year, target.month)[1])
        mtd = sum(v for d, v in account.items() if month_start <= d <= today)
        history = sorted(account)
        window = [d for d in history if today - timedelta(days=base_days) < d <= today]
        projected, variance = 0.0, 0.0
        d = target
        while d <= month_end:
            same = [account[x] for x in window if _is_weekend(x) == _is_weekend(d)]
            mean, std = _stats(same)
            projected += mean
            variance += std ** 2
            d += timedelta(days=1)
        sigma = float(ctx.r("cost_sentinel.band_sigma"))
        forecast = mtd + projected
        band = sigma * math.sqrt(variance)
        full = len(window) >= min_hist
        conf = float(ctx.r("cost_sentinel.forecast_confidence_full_history" if full
                           else "cost_sentinel.forecast_confidence_short_history"))
        month = f"{target.year:04d}-{target.month:02d}"
        return [Finding(
            kind="forecast", subject=month,
            title=f"Month-end forecast {month}: {forecast:.0f} credits (band {forecast - band:.0f}-{forecast + band:.0f})",
            confidence=conf,
            rationale=(f"Month-to-date {mtd:.1f} credits plus {(month_end - today).days} projected day(s) at the "
                       f"trailing {len(window)}-day weekday/weekend means"),
            detail={"month": month, "month_to_date": round(mtd, 2), "projected_remaining": round(projected, 2),
                    "forecast": round(forecast, 2), "low": round(forecast - band, 2), "high": round(forecast + band, 2),
                    "history_days": len(window)},
            evidence=[f"METERING_DAILY_HISTORY:{min(window) if window else today}..{today}"])]
