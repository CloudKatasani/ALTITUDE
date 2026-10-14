"""KPI layer: compute KPI tables from the catalogue, the observed Health Index, and the SEMANTIC layer.

Every KPI table has the uniform shape ``ACCOUNT_NAME, PERIOD, DIMENSION, VALUE`` plus the KPI's declared
``measures``. ``SEMANTIC.KPI_DEFINITIONS`` holds the certified definitions and ``SEMANTIC.KPI_VALUES`` the
long-format union the ask-the-platform agent reads.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Iterable

from altitude.core.ids import content_hash
from altitude.core.rubric import RubricSet, default_rubrics

from .config import kpi_table, load_kpis
from .curate import build_curated, substitute_rubric
from .db import ObsDatabase

HEALTH_WEIGHTS_REF = "rubric.obs.health_index.pillar_weights"
HEALTH_SCALE_REF = "rubric.obs.health_index.scale"

DEF_COLUMNS = {
    "KPI_ID": "VARCHAR", "NAME": "VARCHAR", "DOMAIN": "VARCHAR", "TIER": "VARCHAR", "STATUS": "VARCHAR",
    "CERTIFIED": "BOOLEAN", "DEFINITION": "VARCHAR", "UNIT": "VARCHAR", "GRAIN": "VARCHAR", "DIMENSION_LABEL": "VARCHAR",
    "AGGREGATION": "VARCHAR", "DIRECTION": "VARCHAR", "SOURCES": "VARCHAR", "WAF_PILLAR": "VARCHAR",
    "OWNER_ROLE": "VARCHAR", "KPI_TABLE": "VARCHAR", "SYNONYMS": "VARCHAR", "TARGET": "DOUBLE",
    "DEFINITION_HASH": "VARCHAR", "RUBRIC_VERSION": "VARCHAR",
}

KPI_SHAPE = {"ACCOUNT_NAME": "VARCHAR", "PERIOD": "DATE", "DIMENSION": "VARCHAR", "VALUE": "DOUBLE"}


def implemented(kpis: Iterable[dict] | None = None, engine: str | None = None) -> list[dict]:
    out = [k for k in (kpis if kpis is not None else load_kpis()) if k.get("status") == "implemented"]
    if engine:
        out = [k for k in out if k.get("engine", "sql") == engine]
    return out


def kpi_select(k: dict, rubrics: RubricSet | None = None) -> str:
    """The KPI's SQL wrapped into the uniform KPI table shape (DuckDB dialect)."""
    measures = "".join(f', "{m}"' for m in k.get("measures", []))
    return (
        "SELECT CAST(ACCOUNT_NAME AS VARCHAR) AS ACCOUNT_NAME, CAST(PERIOD AS DATE) AS PERIOD, "
        "coalesce(CAST(DIMENSION AS VARCHAR), '') AS DIMENSION, CAST(VALUE AS DOUBLE) AS VALUE"
        f"{measures} FROM ({substitute_rubric(k['sql'], rubrics)}) k"
    )


def compute_kpis(db: ObsDatabase, rubrics: RubricSet | None = None, *, curate: bool = True) -> dict[str, int]:
    """(Re)build CURATED, every SQL KPI table, the observed Health Index and the SEMANTIC layer."""
    rubrics = rubrics or default_rubrics()
    with db.deterministic():
        if curate:
            build_curated(db)
        kpis = load_kpis()
        counts: dict[str, int] = {}
        for k in implemented(kpis, engine="sql"):
            table = kpi_table(k["id"])
            db.replace_table("KPI", table, kpi_select(k, rubrics))
            counts[k["id"]] = int(db.scalar(f'SELECT count(*) FROM KPI."{table}"'))
        counts.update(compute_health_index(db, kpis, rubrics))
        build_semantic(db, kpis, rubrics)
    return counts


# --------------------------------------------------------------------------- health index


def kpi_target(k: dict, rubrics: RubricSet) -> float | None:
    ref = k.get("target_ref")
    return float(rubrics.get(ref)) if ref else None


def attainment(value: float | None, target: float, direction: str) -> float | None:
    """Score in [0, 1]: how well ``value`` meets ``target`` (1 = at or better than target)."""
    if value is None:
        return None
    if direction == "higher_is_better":
        if target <= 0:
            return 1.0
        return max(0.0, min(1.0, value / target))
    if direction == "lower_is_better":
        if value <= target:
            return 1.0
        if target > 0:
            return max(0.0, min(1.0, target / value))
        return 1.0 / (1.0 + value)
    return None


def daily_series(db: ObsDatabase, k: dict, account: str, start: date | None = None, end: date | None = None,
                 dimension: str | list[str] | None = None) -> dict[date, float]:
    """One value per PERIOD for a KPI: dimensions combined by the KPI's aggregation (sum → sum, else avg)."""
    table = kpi_table(k["id"])
    if not db.relation_exists("KPI", table):
        return {}
    agg = "sum" if k.get("aggregation") == "sum" else "avg"
    where, params = ["ACCOUNT_NAME = ?", "VALUE IS NOT NULL"], [account]
    if start:
        where.append("PERIOD >= ?")
        params.append(start)
    if end:
        where.append("PERIOD <= ?")
        params.append(end)
    if dimension:
        dims = [dimension] if isinstance(dimension, str) else list(dimension)
        where.append(f"DIMENSION IN ({', '.join('?' for _ in dims)})")
        params.extend(dims)
    rows = db.query(f'SELECT PERIOD, {agg}(VALUE) AS V FROM KPI."{table}" WHERE {" AND ".join(where)} '
                    f"GROUP BY PERIOD ORDER BY PERIOD", params)
    return {r["PERIOD"]: float(r["V"]) for r in rows if r["V"] is not None}


def window_value(series: dict[date, float], aggregation: str, start: date, end: date) -> float | None:
    """Aggregate a daily series over ``[start, end]``: sums are averaged per calendar day, latest takes the last."""
    pts = sorted((d, v) for d, v in series.items() if start <= d <= end)
    if not pts:
        return None
    if aggregation == "latest":
        return pts[-1][1]
    if aggregation == "sum":
        return sum(v for _, v in pts) / ((end - start).days + 1)
    if aggregation == "max":
        return max(v for _, v in pts)
    if aggregation == "min":
        return min(v for _, v in pts)
    return sum(v for _, v in pts) / len(pts)


def _month_end(m: date) -> date:
    nxt = date(m.year + (m.month // 12), (m.month % 12) + 1, 1)
    return nxt - timedelta(days=1)


def _targeted(kpis: list[dict], rubrics: RubricSet) -> list[dict]:
    weights = rubrics.get(HEALTH_WEIGHTS_REF)
    return [k for k in implemented(kpis, engine="sql") if k.get("target_ref") and k.get("waf_pillar") in weights]


def _roll_up(pillars: dict[str, list[float]], rubrics: RubricSet) -> tuple[float | None, dict[str, float]]:
    weights: dict[str, float] = {p: float(w) for p, w in rubrics.get(HEALTH_WEIGHTS_REF).items()}
    scale = float(rubrics.get(HEALTH_SCALE_REF))
    pillar_scores = {p: sum(v) / len(v) * scale for p, v in pillars.items() if v}
    total_w = sum(weights[p] for p in pillar_scores)
    if not total_w:
        return None, {}
    return sum(weights[p] * s for p, s in pillar_scores.items()) / total_w, pillar_scores


def health_for_window(db: ObsDatabase, account: str, start: date, end: date, kpis: list[dict] | None = None,
                      rubrics: RubricSet | None = None) -> tuple[float | None, dict[str, float]]:
    """Observed Health Index (0-scale) and pillar scores over ``[start, end]`` for one account."""
    rubrics = rubrics or default_rubrics()
    pillars: dict[str, list[float]] = defaultdict(list)
    for k in _targeted(kpis if kpis is not None else load_kpis(), rubrics):
        series = daily_series(db, k, account, start, end)
        agg = k.get("aggregation", "avg")
        # daily values (summed across dimensions for additive KPIs) averaged over the window
        v = window_value(series, "latest" if agg == "latest" else "avg", start, end)
        score = attainment(v, kpi_target(k, rubrics), k.get("direction", "neutral"))
        if score is not None:
            pillars[k["waf_pillar"]].append(score)
    return _roll_up(pillars, rubrics)


def compute_health_index(db: ObsDatabase, kpis: list[dict], rubrics: RubricSet) -> dict[str, int]:
    targeted = _targeted(kpis, rubrics)
    accounts = [r["ACCOUNT_NAME"] for r in db.query("SELECT DISTINCT ACCOUNT_NAME FROM RAW.HARVEST_LOG ORDER BY 1")]
    overall_rows, pillar_rows = [], []
    for account in accounts:
        per_month: dict[date, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for k in targeted:
            series = daily_series(db, k, account)
            target = kpi_target(k, rubrics)
            agg = k.get("aggregation", "avg")
            for m in sorted({d.replace(day=1) for d in series}):
                monthly = window_value(series, "latest" if agg == "latest" else "avg", m, _month_end(m))
                score = attainment(monthly, target, k.get("direction", "neutral"))
                if score is not None:
                    per_month[m][k["waf_pillar"]].append(score)
        for m, pillars in sorted(per_month.items()):
            phi, pillar_scores = _roll_up(pillars, rubrics)
            if phi is None:
                continue
            overall_rows.append({"ACCOUNT_NAME": account, "PERIOD": m, "DIMENSION": "", "VALUE": round(phi, 4),
                                 "PILLARS": len(pillar_scores)})
            for p, s in sorted(pillar_scores.items()):
                pillar_rows.append({"ACCOUNT_NAME": account, "PERIOD": m, "DIMENSION": p, "VALUE": round(s, 4),
                                    "KPIS": len(pillars[p])})
    db.replace_table_rows("KPI", "KPI_PHI_001", {**KPI_SHAPE, "PILLARS": "INTEGER"}, overall_rows)
    db.replace_table_rows("KPI", "KPI_PHI_002", {**KPI_SHAPE, "KPIS": "INTEGER"}, pillar_rows)
    return {"KPI-PHI-001": len(overall_rows), "KPI-PHI-002": len(pillar_rows)}


# --------------------------------------------------------------------------- semantic layer


def definition_hash(k: dict) -> str:
    keep = {f: k.get(f) for f in ("id", "name", "definition", "unit", "grain", "aggregation", "sql", "engine",
                                  "measures", "direction")}
    return content_hash(keep, 16)


def build_semantic(db: ObsDatabase, kpis: list[dict] | None = None, rubrics: RubricSet | None = None) -> None:
    rubrics = rubrics or default_rubrics()
    kpis = kpis if kpis is not None else load_kpis()
    rows = []
    for k in kpis:
        rows.append({
            "KPI_ID": k["id"], "NAME": k["name"], "DOMAIN": k["domain"], "TIER": k["tier"], "STATUS": k["status"],
            "CERTIFIED": k["status"] == "implemented", "DEFINITION": " ".join(str(k["definition"]).split()),
            "UNIT": k.get("unit"), "GRAIN": json.dumps(k.get("grain", [])), "DIMENSION_LABEL": k.get("dimension"),
            "AGGREGATION": k.get("aggregation"), "DIRECTION": k.get("direction"),
            "SOURCES": json.dumps(k.get("sources", [])), "WAF_PILLAR": k.get("waf_pillar"),
            "OWNER_ROLE": k.get("owner_role"), "KPI_TABLE": f"KPI.{kpi_table(k['id'])}",
            "SYNONYMS": json.dumps(k.get("synonyms", [])), "TARGET": kpi_target(k, rubrics),
            "DEFINITION_HASH": definition_hash(k), "RUBRIC_VERSION": rubrics.version,
        })
    db.replace_table_rows("SEMANTIC", "KPI_DEFINITIONS", DEF_COLUMNS, rows)
    parts = []
    for k in implemented(kpis):
        t = kpi_table(k["id"])
        if db.relation_exists("KPI", t):
            parts.append(f"SELECT '{k['id']}' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM KPI.\"{t}\"")
    if parts:
        db.replace_view("SEMANTIC", "KPI_VALUES", " UNION ALL ".join(parts))
        for dom in sorted({k["domain"] for k in implemented(kpis)}):
            db.replace_view(
                "SEMANTIC", f"SV_{dom.upper()}",
                "SELECT v.KPI_ID, d.NAME, d.UNIT, d.DIMENSION_LABEL, v.ACCOUNT_NAME, v.PERIOD, v.DIMENSION, v.VALUE "
                "FROM SEMANTIC.KPI_VALUES v JOIN SEMANTIC.KPI_DEFINITIONS d ON d.KPI_ID = v.KPI_ID "
                f"WHERE d.DOMAIN = '{dom}' AND d.CERTIFIED")


def kpi_rows(db: ObsDatabase, kpi_id: str, account: str | None = None, start: date | None = None,
             end: date | None = None) -> list[dict[str, Any]]:
    table = kpi_table(kpi_id)
    if not db.relation_exists("KPI", table):
        return []
    where, params = ["TRUE"], []
    if account:
        where.append("ACCOUNT_NAME = ?")
        params.append(account)
    if start:
        where.append("PERIOD >= ?")
        params.append(start)
    if end:
        where.append("PERIOD <= ?")
        params.append(end)
    return db.query(f'SELECT * FROM KPI."{table}" WHERE {" AND ".join(where)} ORDER BY PERIOD, DIMENSION', params)
