"""Suggestion-to-value loop (Section 7.12).

Input: Package D suggestion records (JSON list, shaped like the Section 6.5 record) with ``kpis_to_watch``,
``status: implemented`` and ``implemented_at``. For each implemented suggestion Package O:

1. measures every watched KPI over a *before* window ``[impl - before_days, impl - 1]`` and an *after* window
   ``[impl + settle_days, impl + settle_days + after_days - 1]`` (``rubric.obs.value.*``), restricted to the
   suggestion's ``affected_objects`` when they are KPI dimensions;
2. counts a KPI as improved when it moved in its good direction by at least ``min_improvement_pct``;
3. computes realised value from the watched KPI's ``realised_value.basis_kpi`` (a $ or credit KPI): per-day saving
   between the windows, annualised (credits are priced at the contract price);
4. records the measurement (``obs_value_measurement``) and, when value was realised, the status transition
   ``implemented → value_realised`` (``obs_suggestion_status``) — both append-only;
5. builds the QBR summary: identified vs realised value, outcomes by status and the Health Index delta.

Measurements are deterministic: same OBS data + rubric version ⇒ same measurement id and values.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta
from typing import Any

from altitude.core import audit
from altitude.core.ids import content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import register_append_only

from .config import kpi_index
from .db import ObsDatabase
from .kpi import daily_series, health_for_window, window_value

register_append_only("obs_suggestion_status", "obs_value_measurement")

REF = "rubric.obs.value."


def _d(v: Any) -> date:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def windows(implemented_at: date, rubrics: RubricSet) -> dict[str, date]:
    before = int(rubrics.get(REF + "before_days"))
    settle = int(rubrics.get(REF + "settle_days"))
    after = int(rubrics.get(REF + "after_days"))
    return {"before_start": implemented_at - timedelta(days=before), "before_end": implemented_at - timedelta(days=1),
            "after_start": implemented_at + timedelta(days=settle),
            "after_end": implemented_at + timedelta(days=settle + after - 1)}


def _dims_for(db: ObsDatabase, kpi_id: str, account: str, affected: list[str]) -> list[str] | None:
    if not affected:
        return None
    table = kpi_id.replace("-", "_")
    if not db.relation_exists("KPI", table):
        return None
    dims = {r["DIMENSION"] for r in db.query(f'SELECT DISTINCT DIMENSION FROM KPI."{table}" WHERE ACCOUNT_NAME = ?',
                                               [account])}
    hit = sorted(dims & set(affected))
    return hit or None


def _coverage(series: dict[date, float], start: date, end: date) -> float:
    days = (end - start).days + 1
    return len([d for d in series if start <= d <= end]) / days if days > 0 else 0.0


def measure_suggestion(db: ObsDatabase, s: dict, account: str, rubrics: RubricSet | None = None) -> dict:
    """Before/after measurement of one implemented suggestion (no persistence)."""
    rubrics = rubrics or default_rubrics()
    kpis = kpi_index()
    impl = _d(s["implemented_at"])
    w = windows(impl, rubrics)
    min_pct = float(rubrics.get(REF + "min_improvement_pct"))
    min_cov = float(rubrics.get(REF + "min_coverage"))
    latest = db.scalar("SELECT max(PERIOD) FROM SEMANTIC.KPI_VALUES WHERE ACCOUNT_NAME = ?", [account])
    affected = list(s.get("affected_objects") or [])
    results, evidence = [], []
    for kid in s.get("kpis_to_watch") or []:
        k = kpis.get(kid)
        if not k or k.get("status") != "implemented":
            results.append({"kpi_id": kid, "status": "not_measurable", "reason": "KPI not certified"})
            continue
        dims = _dims_for(db, kid, account, affected)
        series = daily_series(db, k, account, w["before_start"], w["after_end"], dims)
        agg = k.get("aggregation", "avg")
        b = window_value(series, agg, w["before_start"], w["before_end"])
        a = window_value(series, agg, w["after_start"], w["after_end"])
        cov_b = _coverage(series, w["before_start"], w["before_end"])
        cov_a = _coverage(series, w["after_start"], w["after_end"])
        complete = latest is not None and _d(latest) >= w["after_end"]
        status = "measured"
        if not complete or b is None or a is None or min(cov_b, cov_a) < min_cov:
            status = "insufficient_data"
        delta = None if (a is None or b is None) else a - b
        pct = None if delta is None or not b else delta / abs(b) * 100.0
        direction = k.get("direction", "neutral")
        improved = bool(status == "measured" and pct is not None and (
            (direction == "lower_is_better" and -pct >= min_pct) or (direction == "higher_is_better" and pct >= min_pct)))
        results.append({"kpi_id": kid, "status": status, "dimensions": dims, "aggregation": agg, "before": b,
                        "after": a, "delta": delta, "delta_pct": pct, "direction": direction, "improved": improved,
                        "coverage_before": round(cov_b, 4), "coverage_after": round(cov_a, 4)})
        evidence.append([kid, dims, sorted((d.isoformat(), round(v, 9)) for d, v in series.items())])

    realised_usd, method = 0.0, "no watched KPI improved"
    if any(r.get("improved") for r in results):
        basis_id = next((kpis[r["kpi_id"]].get("realised_value", {}).get("basis_kpi") for r in results
                         if r.get("improved") and kpis[r["kpi_id"]].get("realised_value")), None)
        if basis_id:
            basis = kpis[basis_id]
            dims = _dims_for(db, basis_id, account, affected)
            series = daily_series(db, basis, account, w["before_start"], w["after_end"], dims)
            per_day_b = window_value(series, "sum", w["before_start"], w["before_end"]) or 0.0
            per_day_a = window_value(series, "sum", w["after_start"], w["after_end"]) or 0.0
            factor = 1.0
            if basis.get("unit") == "credits":
                factor = float(db.scalar("SELECT max(PRICE_PER_CREDIT) FROM CURATED.DIM_ACCOUNT WHERE ACCOUNT_NAME = ?",
                                         [account]) or 0.0)
            days = int(rubrics.get(REF + "annualisation_days"))
            realised_usd = round(max(0.0, per_day_b - per_day_a) * factor * days, 2)
            method = (f"({basis_id} per-day {'$' if factor == 1.0 else 'credits x contract price'} before "
                      f"{w['before_start']}..{w['before_end']} − after {w['after_start']}..{w['after_end']}"
                      f"{' on ' + ', '.join(dims) if dims else ''}) × {days} days")
            evidence.append([basis_id, dims, sorted((d.isoformat(), round(v, 9)) for d, v in series.items())])
        else:
            method = "watched KPI improved; no monetary basis KPI defined (risk value)"
    statuses = {r["status"] for r in results}
    if "measured" not in statuses:
        outcome = "insufficient_data"
    elif any(r.get("improved") for r in results):
        outcome = "value_realised"
    else:
        outcome = "no_improvement"
    identified = float(((s.get("value") or {}).get("annualised_usd") or {}).get("p50") or 0.0)
    ev_hash = content_hash(evidence, 32)
    return {
        "measurement_id": stable_id("VAL", s["id"], impl.isoformat(), account, rubrics.version, ev_hash),
        "suggestion_id": s["id"], "check_id": s.get("check_id"), "account_name": account,
        "affected_objects": affected, "implemented_at": impl, **w, "kpi_results": results,
        "identified_usd": identified, "realised_usd": realised_usd, "realised_method": method, "outcome": outcome,
        "rubric_version": rubrics.version, "evidence_hash": ev_hash,
    }


def measure_suggestions(db: ObsDatabase, suggestions: list[dict], *, store: Any = None, account: str | None = None,
                        tenant_id: str | None = None, actor: str = "obs-value-loop",
                        rubrics: RubricSet | None = None, measured_at: datetime | None = None) -> list[dict]:
    """Measure every implemented suggestion; persist to ``store`` and return the updated suggestion records."""
    rubrics = rubrics or default_rubrics()
    accounts = [r["ACCOUNT_NAME"] for r in db.query("SELECT DISTINCT ACCOUNT_NAME FROM SEMANTIC.KPI_VALUES ORDER BY 1")]
    out = []
    for s in suggestions:
        rec = json.loads(json.dumps(s, default=str))
        if s.get("status") != "implemented" or not s.get("implemented_at"):
            out.append(rec)
            continue
        acct = s.get("account_name") or account or (accounts[0] if len(accounts) == 1 else None)
        if acct is None:
            raise ValueError(f"suggestion {s['id']}: account_name is required with several accounts in the archive")
        m = measure_suggestion(db, s, acct, rubrics)
        when = measured_at or datetime.combine(m["after_end"] + timedelta(days=1), time())
        if store is not None:
            _persist(store, m, tenant_id, actor, when)
        rec["value"] = {**(rec.get("value") or {}), "realised": {
            "annualised_usd": m["realised_usd"], "method": m["realised_method"], "measurement_id": m["measurement_id"],
            "outcome": m["outcome"], "measured_kpis": [
                {k: r.get(k) for k in ("kpi_id", "before", "after", "delta_pct", "improved", "status")}
                for r in m["kpi_results"]]}}
        if m["outcome"] == "value_realised":
            rec["status"] = "value_realised"
        rec["measurement"] = json.loads(json.dumps(m, default=str))
        out.append(rec)
    return out


def _persist(store: Any, m: dict, tenant_id: str | None, actor: str, when: datetime) -> None:
    if not store.get("obs_value_measurement", measurement_id=m["measurement_id"]):
        store.insert("obs_value_measurement", {
            "measurement_id": m["measurement_id"], "tenant_id": tenant_id, "suggestion_id": m["suggestion_id"],
            "check_id": m["check_id"], "account_name": m["account_name"],
            "affected_objects": json.dumps(m["affected_objects"]), "implemented_at": m["implemented_at"],
            "before_start": m["before_start"], "before_end": m["before_end"], "after_start": m["after_start"],
            "after_end": m["after_end"], "kpi_results": json.dumps(m["kpi_results"], default=str),
            "identified_usd": m["identified_usd"], "realised_usd": m["realised_usd"],
            "realised_method": m["realised_method"], "outcome": m["outcome"], "rubric_version": m["rubric_version"],
            "evidence_hash": m["evidence_hash"], "measured_at": when,
        })
    if m["outcome"] != "value_realised":
        return
    tid = stable_id("STS", m["suggestion_id"], "implemented", "value_realised", m["measurement_id"])
    if store.get("obs_suggestion_status", transition_id=tid):
        return
    store.insert("obs_suggestion_status", {
        "transition_id": tid, "tenant_id": tenant_id, "suggestion_id": m["suggestion_id"], "check_id": m["check_id"],
        "from_status": "implemented", "to_status": "value_realised", "measurement_id": m["measurement_id"],
        "actor": actor, "actor_type": "system",
        "reason": f"realised ${m['realised_usd']:,.0f}/yr measured in-account ({m['realised_method']})",
        "transitioned_at": when,
    })
    audit.record(store, actor, "suggestion.value_realised", actor_type="system", subject_type="suggestion",
                 subject_id=m["suggestion_id"], details={"measurement_id": m["measurement_id"],
                                                         "realised_usd": m["realised_usd"]}, tenant_id=tenant_id)


def current_status(store: Any, suggestion_id: str) -> str | None:
    rows = store.query("SELECT to_status FROM obs_suggestion_status WHERE suggestion_id = ? "
                       "ORDER BY transitioned_at DESC, transition_id DESC LIMIT 1", [suggestion_id])
    return rows[0]["to_status"] if rows else None


def qbr_summary(db: ObsDatabase, measured: list[dict], *, account: str | None = None,
                baseline_health_index: float | None = None, store: Any = None, tenant_id: str | None = None,
                rubrics: RubricSet | None = None) -> dict:
    """Quarterly business review: identified vs realised value and the Health Index delta."""
    rubrics = rubrics or default_rubrics()
    live = [s for s in measured if s.get("status") != "rejected"]
    identified = sum(float(((s.get("value") or {}).get("annualised_usd") or {}).get("p50") or 0.0) for s in live)
    realised = sum(float(((s.get("value") or {}).get("realised") or {}).get("annualised_usd") or 0.0)
                   for s in live if s.get("status") == "value_realised")
    by_status: dict[str, int] = {}
    for s in measured:
        by_status[s.get("status", "unknown")] = by_status.get(s.get("status", "unknown"), 0) + 1
    accounts = [r["ACCOUNT_NAME"] for r in db.query("SELECT DISTINCT ACCOUNT_NAME FROM SEMANTIC.KPI_VALUES ORDER BY 1")]
    acct = account or (accounts[0] if accounts else None)
    impl = sorted(_d(s["implemented_at"]) for s in measured if s.get("implemented_at"))
    latest = db.scalar("SELECT max(PERIOD) FROM SEMANTIC.KPI_VALUES WHERE ACCOUNT_NAME = ?", [acct]) if acct else None
    hi_before = hi_after = None
    pillars_before: dict[str, float] = {}
    pillars_after: dict[str, float] = {}
    period = None
    if acct and impl and latest:
        wb = windows(impl[0], rubrics)
        span = (wb["after_end"] - wb["after_start"]).days
        after_end = _d(latest)
        hi_before, pillars_before = health_for_window(db, acct, wb["before_start"], wb["before_end"], rubrics=rubrics)
        hi_after, pillars_after = health_for_window(db, acct, after_end - timedelta(days=span), after_end, rubrics=rubrics)
        period = (wb["before_start"], after_end)
    baseline = baseline_health_index if baseline_health_index is not None else hi_before
    summary = {
        "account": acct, "period": [p.isoformat() for p in period] if period else None,
        "suggestions": len(measured), "by_status": dict(sorted(by_status.items())),
        "identified_usd": round(identified, 2), "realised_usd": round(realised, 2),
        "realisation_rate": round(realised / identified, 4) if identified else None,
        "health_index": {
            "baseline": None if baseline is None else round(baseline, 2),
            "baseline_source": "package_d" if baseline_health_index is not None else "observed_before_window",
            "current": None if hi_after is None else round(hi_after, 2),
            "delta": None if (baseline is None or hi_after is None) else round(hi_after - baseline, 2),
            "pillars_before": {k: round(v, 2) for k, v in sorted(pillars_before.items())},
            "pillars_after": {k: round(v, 2) for k, v in sorted(pillars_after.items())},
        },
        "items": [{"id": s["id"], "check_id": s.get("check_id"), "status": s.get("status"),
                   "identified_usd": float(((s.get("value") or {}).get("annualised_usd") or {}).get("p50") or 0.0),
                   "realised_usd": float(((s.get("value") or {}).get("realised") or {}).get("annualised_usd") or 0.0),
                   "outcome": ((s.get("value") or {}).get("realised") or {}).get("outcome")} for s in measured],
        "rubric_version": rubrics.version,
    }
    summary["qbr_id"] = stable_id("QBR", tenant_id, acct, summary["period"], content_hash(summary["items"]))
    if store is not None and not store.get("obs_qbr_summary", qbr_id=summary["qbr_id"]):
        store.insert("obs_qbr_summary", {
            "qbr_id": summary["qbr_id"], "tenant_id": tenant_id,
            "period_start": period[0] if period else None, "period_end": period[1] if period else None,
            "identified_usd": summary["identified_usd"], "realised_usd": summary["realised_usd"],
            "health_index_before": summary["health_index"]["baseline"],
            "health_index_after": summary["health_index"]["current"],
            "summary": json.dumps(summary, default=str, sort_keys=True),
            "created_at": datetime.combine(period[1], time()) if period else datetime(1970, 1, 1),
        })
    return summary
