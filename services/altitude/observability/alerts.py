"""Alert evaluation (Section 7.6): rules from ``knowledge/observability/alerts.yaml`` over the KPI layer.

``evaluate_alerts(db, registry, day, outbox)`` evaluates every alert for every account for ``day``:

- ``forecast_band``: baseline = the KPI's values on days of the same type (weekday / weekend) in the rubric
  lookback before ``day``; expected = mean, band = max(k·stdev, min_band_pct·mean). Fires when the value is above
  ``expected + band`` and exceeds ``expected`` by at least the rubric minimum.
- ``threshold``: the KPI value for ``day`` (or its month for monthly KPIs) compared with a rubric threshold.
- ``query``: SQL over CURATED returning the firing items.

Fired events go to ``OPS.ALERT_EVENT`` (append-only); a repeat of the same alert, account and dimension inside
the alert's suppression window is recorded as ``suppressed`` and not routed. Routed payloads are written to the
outbox by :mod:`.routing`.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import kpi_index, kpi_table, load_alerts, load_registry, resolve_route
from .curate import substitute_rubric
from .db import ObsDatabase
from .routing import build_payload, write_outbox

_OPS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
}


@dataclass
class Firing:
    dimension: str
    observed: float | None
    message: str
    expected: float | None = None
    upper: float | None = None
    evidence: dict | None = None


def _day_type(d: date) -> bool:
    """Seasonality key for the forecast band: weekend (Saturday/Sunday) vs weekday."""
    return d.weekday() in (5, 6)


def _series_by_dim(db: ObsDatabase, kpi_id: str, account: str, start: date, end: date, per: str) -> dict[str, dict[date, float]]:
    table = kpi_table(kpi_id)
    if not db.relation_exists("KPI", table):
        return {}
    dim = "DIMENSION" if per == "dimension" else "''"
    rows = db.query(
        f'SELECT {dim} AS DIM, PERIOD, sum(VALUE) AS V FROM KPI."{table}" '
        "WHERE ACCOUNT_NAME = ? AND PERIOD >= ? AND PERIOD <= ? AND VALUE IS NOT NULL GROUP BY 1, 2", [account, start, end])
    out: dict[str, dict[date, float]] = {}
    for r in rows:
        out.setdefault(r["DIM"], {})[r["PERIOD"]] = float(r["V"])
    return out


def forecast_band(history: list[float], rubrics: RubricSet, rule: dict) -> tuple[float, float] | None:
    """``(expected, upper)`` from baseline values, or None when there is not enough history."""
    if len(history) < int(rubrics.get(rule["min_points_ref"])):
        return None
    mean = statistics.fmean(history)
    sd = statistics.pstdev(history) if len(history) > 1 else 0.0
    band = max(float(rubrics.get(rule["band_stdevs_ref"])) * sd, float(rubrics.get(rule["min_band_pct_ref"])) * abs(mean))
    return mean, mean + band


def _eval_forecast_band(db, alert, account, day, rubrics) -> list[Firing]:
    rule = alert["rule"]
    lookback = int(rubrics.get(rule["lookback_ref"]))
    min_abs = float(rubrics.get(rule["min_abs_ref"]))
    series = _series_by_dim(db, alert["kpi"], account, day - timedelta(days=lookback), day, rule.get("per", "dimension"))
    out = []
    for dim, s in sorted(series.items()):
        if day not in s:
            continue
        history = [v for d, v in s.items() if d < day and _day_type(d) == _day_type(day)]
        fb = forecast_band(history, rubrics, rule)
        if fb is None:
            continue
        expected, upper = fb
        actual = s[day]
        if actual > upper and actual - expected >= min_abs:
            unit = kpi_index().get(alert["kpi"], {}).get("unit", "")
            label = dim or account
            out.append(Firing(dim, actual, f"{label}: {alert['kpi']} = {actual:,.2f} {unit} on {day} vs forecast "
                                           f"{expected:,.2f} (band upper {upper:,.2f}, {len(history)} baseline days)",
                              expected, upper, {"baseline_days": sorted(d.isoformat() for d in s if d < day
                                                                         and _day_type(d) == _day_type(day))}))
    return out


def _eval_threshold(db, alert, account, day, rubrics) -> list[Firing]:
    rule = alert["rule"]
    threshold = float(rubrics.get(rule["threshold_ref"]))
    op = _OPS[rule.get("op", "gt")]
    table = kpi_table(alert["kpi"])
    if not db.relation_exists("KPI", table):
        return []
    period = day.replace(day=1) if rule.get("at") == "month" else day
    rows = db.query(f'SELECT DIMENSION, VALUE FROM KPI."{table}" WHERE ACCOUNT_NAME = ? AND PERIOD = ? '
                    "AND VALUE IS NOT NULL ORDER BY DIMENSION", [account, period])
    name = kpi_index().get(alert["kpi"], {}).get("name", alert["kpi"])
    return [Firing(r["DIMENSION"], float(r["VALUE"]),
                   f"{(r['DIMENSION'] or account)}: {name} = {float(r['VALUE']):,.4g} on {period} "
                   f"({rule.get('op', 'gt')} {threshold:g})", None, threshold)
            for r in rows if op(float(r["VALUE"]), threshold)]


def _eval_query(db, alert, account, day, rubrics) -> list[Firing]:
    sql = substitute_rubric(alert["rule"]["sql"], rubrics)
    rows = db.query(sql, {"account": account, "day": day})
    return [Firing(str(r["DIMENSION"] or ""), None if r.get("OBSERVED") is None else float(r["OBSERVED"]),
                   str(r["MESSAGE"])) for r in rows]


EVALUATORS = {"forecast_band": _eval_forecast_band, "threshold": _eval_threshold, "query": _eval_query}


def evaluate_alerts(db: ObsDatabase, registry: dict | str | None, day: date, outbox: str | Path | None = None, *,
                    accounts: list[str] | None = None, rubrics: RubricSet | None = None,
                    alert_ids: list[str] | None = None) -> list[dict]:
    """Evaluate the alert catalogue for ``day``; returns the event records (fired and suppressed)."""
    rubrics = rubrics or default_rubrics()
    reg = registry if isinstance(registry, dict) else load_registry(registry)
    cat = load_alerts()
    severities = cat.get("severities", {})
    if accounts is None:
        accounts = [a["account_name"] for a in reg.get("accounts", [])]
        present = {r["ACCOUNT_NAME"] for r in db.query("SELECT DISTINCT ACCOUNT_NAME FROM RAW.HARVEST_LOG")}
        accounts = [a for a in accounts if a in present]
    events = []
    for alert in cat["alerts"]:
        if alert_ids and alert["id"] not in alert_ids:
            continue
        route_name, route = resolve_route(reg, alert["route_ref"])
        window = timedelta(hours=float(alert.get("suppression_hours", 0)))
        for account in accounts:
            for f in EVALUATORS[alert["rule"]["type"]](db, alert, account, day, rubrics):
                event_id = stable_id("ALE", alert["id"], account, f.dimension, day.isoformat())
                if db.query("SELECT 1 FROM OPS.ALERT_EVENT WHERE EVENT_ID = ?", [event_id]):
                    events.extend(db.query("SELECT * FROM OPS.ALERT_EVENT WHERE EVENT_ID = ?", [event_id]))
                    continue
                since = datetime.combine(day, datetime.min.time()) - window
                prior = db.query(
                    "SELECT EVENT_ID FROM OPS.ALERT_EVENT WHERE ALERT_ID = ? AND ACCOUNT_NAME = ? AND DIMENSION = ? "
                    "AND STATUS = 'fired' AND EVALUATED_FOR < ? AND CAST(EVALUATED_FOR AS TIMESTAMP) > ?",
                    [alert["id"], account, f.dimension, day, since])
                status = "suppressed" if prior else "fired"
                event = {
                    "EVENT_ID": event_id, "ALERT_ID": alert["id"], "ALERT_CLASS": alert["class"],
                    "ALERT_NAME": alert["name"], "ACCOUNT_NAME": account, "DIMENSION": f.dimension,
                    "EVALUATED_FOR": day, "SEVERITY": alert["severity"], "ROUTE": route_name,
                    "CHANNEL": route["channel"], "RUNBOOK": alert["runbook"], "OWNER_ROLE": alert["owner_role"],
                    "STATUS": status, "OBSERVED": f.observed, "EXPECTED": f.expected, "UPPER_BAND": f.upper,
                    "MESSAGE": f.message,
                    "EVIDENCE": json.dumps({"kpi": alert["kpi"], "kpi_table": f"KPI.{kpi_table(alert['kpi'])}",
                                            "rule": alert["rule"]["type"], **(f.evidence or {})}, sort_keys=True),
                    "OUTBOX_PATH": None,
                }
                if status == "fired" and outbox is not None:
                    payload = build_payload({**event, "EVALUATED_FOR": day.isoformat()}, route, severities)
                    event["OUTBOX_PATH"] = write_outbox(outbox, route["channel"], event_id, payload)
                db.append_ops("ALERT_EVENT", [{k: v for k, v in event.items() if k != "ALERT_NAME"}])
                events.append(event)
    return events


def alert_history(db: ObsDatabase, start: date | None = None, end: date | None = None) -> list[dict[str, Any]]:
    where, params = ["TRUE"], []
    if start:
        where.append("EVALUATED_FOR >= ?")
        params.append(start)
    if end:
        where.append("EVALUATED_FOR <= ?")
        params.append(end)
    return db.query(f"SELECT * FROM OPS.ALERT_EVENT WHERE {' AND '.join(where)} ORDER BY EVALUATED_FOR, ALERT_ID", params)
