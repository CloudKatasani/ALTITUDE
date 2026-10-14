"""Anonymised peer benchmarks: consent-gated contributions, cohort quartiles only above a minimum sample."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics


class ConsentRequired(Exception):
    pass


def _contributor_hash(tenant_id: str) -> str:
    salt = os.environ.get("ALTITUDE_BENCHMARK_SALT", "altitude-benchmark")
    return hashlib.sha256(f"{salt}|{tenant_id}".encode()).hexdigest()[:20]


def contribute(store: Any, tenant_id: str, consent_ref: str | None, industry: str, spend_band: str, period: str,
               metrics: dict[str, float]) -> int:
    """Store anonymised metric values. Nothing is contributed without a consent reference."""
    if not consent_ref:
        raise ConsentRequired("benchmark contributions require the client's opt-in consent reference")
    who = _contributor_hash(tenant_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = []
    for metric, value in sorted(metrics.items()):
        oid = stable_id("BMK", who, metric, period)
        if store.get("benchmark_observation", observation_id=oid):
            continue
        rows.append({"observation_id": oid, "contributor_hash": who, "industry": industry, "spend_band": spend_band,
                     "metric": metric, "value": float(value), "period": period, "consent_ref": consent_ref,
                     "contributed_at": now})
    return store.insert("benchmark_observation", rows)


def position(store: Any, metric: str, value: float, industry: str, spend_band: str | None = None,
             lower_is_better: bool = True, rubrics: RubricSet | None = None) -> dict:
    """Quartile position of ``value`` within its cohort (latest value per contributor)."""
    rubrics = rubrics or default_rubrics()
    min_n = int(rubrics.get("rubric.benchmark.min_contributors"))
    params: list = [metric, industry]
    band_sql = ""
    if spend_band:
        band_sql = " AND spend_band = ?"
        params.append(spend_band)
    rows = store.query(
        "SELECT contributor_hash, arg_max(value, period) AS v FROM benchmark_observation "
        f"WHERE metric = ? AND industry = ?{band_sql} GROUP BY contributor_hash", params)
    vals = sorted(float(r["v"]) for r in rows)
    if len(vals) < min_n:
        return {"metric": metric, "cohort_size": len(vals), "published": False,
                "reason": f"cohort below the minimum of {min_n} contributors"}
    better = sum(1 for v in vals if (v > value if lower_is_better else v < value))
    pct_better_than = better / len(vals)
    quartile = 1 + min(3, int((1 - pct_better_than) * 4))  # 1 = best quartile
    q = [vals[int(round(p * (len(vals) - 1)))] for p in (0.25, 0.5, 0.75)]  # threshold-ok: quartile cut points
    return {"metric": metric, "cohort_size": len(vals), "published": True, "quartile": quartile,
            "better_than_share": round(pct_better_than, 3), "p25": q[0], "median": q[1], "p75": q[2],
            "label": ["best", "second", "third", "worst"][quartile - 1] + " quartile"}
