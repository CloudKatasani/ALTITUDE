"""Static HTML dashboards (Section 7.5: 1 Executive Cost & Value, 2 Platform Health, 4 Pipelines & Freshness)
and dashboard 8 — monthly chargeback statements per cost centre — rendered from the KPI tables.

Templates live in ``templates/`` and use ``{{TOKEN}}`` theme placeholders only (white-label); charts are
inline SVG styled through the template's CSS variables, so no colour or brand literal appears in code.
Rendering is deterministic: the "as of" date comes from the data, never the wall clock.
"""

from __future__ import annotations

import html
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.theme import render

from .config import load_registry
from .db import ObsDatabase
from .harvest import freshness
from .kpi import implemented, kpi_target, window_value, daily_series

TEMPLATES = Path(__file__).parent / "templates"
AMBER_REF = "rubric.obs.kpi_targets.amber_band"
UNALLOCATED_SHARE_REF = "rubric.obs.chargeback.unallocated_label_max_share"

DASHBOARDS = [
    ("executive_cost_value.html", "Executive Cost & Value"),
    ("platform_health.html", "Platform Health"),
    ("pipelines_freshness.html", "Pipelines & Freshness"),
    ("chargeback/index.html", "Chargeback statements"),
]


def esc(v: Any) -> str:
    return html.escape(str(v), quote=True)


def fmt(v: float | None, unit: str | None = None) -> str:
    if v is None:
        return "–"
    if unit == "usd":
        return f"${v:,.0f}"
    if unit == "ratio":
        return f"{v * 100:.1f}%"
    if unit == "percent":
        return f"{v:+.1f}%"
    if unit in ("credits", "gb", "tb", "seconds", "ms"):
        return f"{v:,.1f} {unit}"
    return f"{v:,.2f}" if isinstance(v, float) and not float(v).is_integer() else f"{v:,.0f}"


# --------------------------------------------------------------------------- SVG charts


def line_chart(points: list[tuple[str, float]], *, unit: str | None = None, target: float | None = None) -> str:
    if not points:
        return '<p class="empty">No data in the window.</p>'
    w, h, left, bottom, top = 640, 220, 56, 28, 12
    vals = [v for _, v in points] + ([target] if target is not None else [])
    hi = max(vals) or 1.0
    lo = min(0.0, min(vals))
    span = (hi - lo) or 1.0
    n = len(points)
    step = (w - left - 8) / (n - 1 if n > 1 else 1)

    def y(v: float) -> float:
        return top + (h - top - bottom) * (1 - (v - lo) / span)

    coords = [(left + i * step, y(v)) for i, (_, v) in enumerate(points)]
    path = " ".join(f"{'M' if i == 0 else 'L'}{x:.1f},{yy:.1f}" for i, (x, yy) in enumerate(coords))
    area = path + f" L{coords[-1][0]:.1f},{y(lo):.1f} L{coords[0][0]:.1f},{y(lo):.1f} Z"
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    for frac in (0.0, 0.5, 1.0):
        v = lo + span * frac
        parts.append(f'<line class="grid-line" x1="{left}" x2="{w - 8}" y1="{y(v):.1f}" y2="{y(v):.1f}"/>'
                     f'<text class="muted" x="{left - 6}" y="{y(v) + 4:.1f}" text-anchor="end">{esc(fmt(v, unit))}</text>')
    parts.append(f'<path class="area" d="{area}"/><path class="line" d="{path}"/>')
    if target is not None:
        parts.append(f'<line class="target" x1="{left}" x2="{w - 8}" y1="{y(target):.1f}" y2="{y(target):.1f}"/>')
    every = max(1, n // 6)
    for i, (label, _) in enumerate(points):
        if i % every == 0 or i == n - 1:
            parts.append(f'<text class="muted" x="{left + i * step:.1f}" y="{h - 8}" text-anchor="middle">{esc(label)}</text>')
    parts.append(f'<line class="axis" x1="{left}" x2="{w - 8}" y1="{y(lo):.1f}" y2="{y(lo):.1f}"/></svg>')
    return "".join(parts)


def bar_chart(items: list[tuple[str, float]], *, unit: str | None = None, classes: list[str] | None = None) -> str:
    if not items:
        return '<p class="empty">No data in the window.</p>'
    row, label_w, w = 24, 170, 640
    h = row * len(items) + 8
    hi = max((v for _, v in items), default=0.0) or 1.0
    parts = [f'<svg viewBox="0 0 {w} {h}" role="img">']
    for i, (label, v) in enumerate(items):
        bw = (w - label_w - 90) * max(0.0, v) / hi
        cls = f"bar {classes[i]}" if classes and classes[i] else "bar"
        y0 = 4 + i * row
        parts.append(f'<text x="{label_w - 8}" y="{y0 + 15}" text-anchor="end">{esc(label)}</text>'
                     f'<rect class="{cls}" x="{label_w}" y="{y0 + 3}" width="{bw:.1f}" height="{row - 8}" rx="2"/>'
                     f'<text x="{label_w + bw + 6:.1f}" y="{y0 + 15}">{esc(fmt(v, unit))}</text>')
    parts.append("</svg>")
    return "".join(parts)


def table(headers: list[str], rows: Iterable[list[Any]], numeric: set[int] | None = None,
          total: list[Any] | None = None) -> str:
    numeric = numeric or set()
    head = "".join(f'<th class="num">{esc(h)}</th>' if i in numeric else f"<th>{esc(h)}</th>"
                   for i, h in enumerate(headers))
    body = []
    for r in list(rows) + ([total] if total else []):
        cls = ' class="total"' if total is not None and r is total else ""
        body.append(f"<tr{cls}>" + "".join(f'<td class="num">{c}</td>' if i in numeric else f"<td>{c}</td>"
                                           for i, c in enumerate(r)) + "</tr>")
    if not body:
        return '<p class="empty">Nothing to report.</p>'
    return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def tile(label: str, value: str, note: str = "", state: str = "") -> str:
    return (f'<div class="tile {state}"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div>'
            f'<div class="note">{esc(note)}</div></div>')


def card(title: str, kpi_ids: str, body: str) -> str:
    return f'<section class="card"><h2>{esc(title)}</h2><div class="kpi-ref">{esc(kpi_ids)}</div>{body}</section>'


def page(title: str, subtitle: str, body: str, footer: str, theme: str | None, depth: int = 0) -> str:
    up = "../" * depth
    nav = " ".join(f'<a href="{up}{f}">{esc(t)}</a>' for f, t in DASHBOARDS)
    tpl = (TEMPLATES / "dashboard.html").read_text()
    # extras first, then a theme pass so {{TOKENS}} inside generated fragments resolve too
    return render(render(tpl, theme, TITLE=esc(title), SUBTITLE=esc(subtitle), NAV=nav, BODY=body,
                         FOOTER=esc(footer)), theme)


# --------------------------------------------------------------------------- data helpers


def _sum_by(db: ObsDatabase, table: str, start: date, end: date, account: str | None, group: str = "DIMENSION"):
    acc = " AND ACCOUNT_NAME = ?" if account else ""
    return db.query(f'SELECT {group} AS K, sum(VALUE) AS V FROM KPI."{table}" WHERE PERIOD BETWEEN ? AND ?{acc} '
                    f"GROUP BY 1 ORDER BY V DESC, K", [start, end] + ([account] if account else []))


def _daily_total(db: ObsDatabase, table: str, start: date, end: date, account: str | None) -> list[tuple[str, float]]:
    rows = _sum_by(db, table, start, end, account, group="PERIOD")
    return [(r["K"].strftime("%m-%d"), float(r["V"] or 0)) for r in sorted(rows, key=lambda r: r["K"])]


def _latest(db: ObsDatabase, table: str, account: str | None, on_or_before: date) -> dict | None:
    acc = " AND ACCOUNT_NAME = ?" if account else ""
    rows = db.query(f'SELECT * FROM KPI."{table}" WHERE PERIOD <= ? AND VALUE IS NOT NULL{acc} '
                    f"ORDER BY PERIOD DESC, ACCOUNT_NAME LIMIT 1", [on_or_before] + ([account] if account else []))
    return rows[0] if rows else None


def rag(value: float | None, target: float | None, direction: str, amber: float) -> str:
    if value is None or target is None:
        return "none"
    if direction == "higher_is_better":
        if value >= target:
            return "green"
        return "amber" if value >= target * (1 - amber) else "red"
    if value <= target:
        return "green"
    return "amber" if value <= target * (1 + amber) else "red"


def _pillar_class(score: float, rs: RubricSet) -> str:
    if score < float(rs.get("rubric.obs.dashboard.pillar_red_below")):
        return "bad"
    return "warn" if score < float(rs.get("rubric.obs.dashboard.pillar_amber_below")) else "alt"


# --------------------------------------------------------------------------- dashboards


def executive_cost_value(db, as_of: date, account: str | None, theme: str | None, window_days: int,
                         value_summary: dict | None = None) -> str:
    start = as_of - timedelta(days=window_days - 1)
    month = as_of.replace(day=1)
    mtd = sum(v for _, v in _daily_total(db, "KPI_COST_011", month, as_of, account))
    mom = _latest(db, "KPI_COST_004", account, as_of)
    fvb = _latest(db, "KPI_COST_005", account, as_of)
    cc = _sum_by(db, "KPI_COST_003", start, as_of, account)
    total_cc = sum(float(r["V"] or 0) for r in cc) or 0.0
    unalloc = sum(float(r["V"] or 0) for r in cc if r["K"] == "UNALLOCATED")
    attributed = (1 - unalloc / total_cc) if total_cc else None
    rs = default_rubrics()
    fvb_state = "" if not fvb or fvb["VALUE"] is None else (
        "bad" if fvb["VALUE"] >= float(rs.get("rubric.obs.alerts.budget_breach_ratio")) else
        "warn" if fvb["VALUE"] >= float(rs.get("rubric.obs.alerts.budget_warn_ratio")) else "")
    attr_state = "" if attributed is None or 1 - attributed <= float(rs.get(UNALLOCATED_SHARE_REF)) else "warn"
    tiles = [
        tile("Spend month to date", fmt(mtd, "usd"), f"{month:%B %Y} · KPI-COST-011"),
        tile("Month-on-month", fmt(mom["VALUE"], "percent") if mom else "–", "avg daily spend · KPI-COST-004"),
        tile("Forecast vs budget", fmt(fvb["VALUE"], "ratio") if fvb else "–", "month-end forecast · KPI-COST-005",
             fvb_state),
        tile("Spend attributed", fmt(attributed, "ratio"), "to a cost centre · KPI-COST-003", attr_state),
    ]
    if value_summary:
        tiles.append(tile("Value realised", fmt(value_summary.get("realised_usd"), "usd"),
                          f"of {fmt(value_summary.get('identified_usd'), 'usd')} identified (annualised)"))
    wh = _sum_by(db, "KPI_COST_002", start, as_of, account)
    sig = _sum_by(db, "KPI_COST_006", start, as_of, account)[:10]
    sl = _sum_by(db, "KPI_COST_008", start, as_of, account)
    body = (
        f'<div class="tiles">{"".join(tiles)}</div><div class="grid">'
        + card(f"Daily spend, last {window_days} days", "KPI-COST-011",
               line_chart(_daily_total(db, "KPI_COST_011", start, as_of, account), unit="usd"))
        + card("Spend by warehouse", "KPI-COST-002",
               bar_chart([(r["K"], float(r["V"] or 0)) for r in wh], unit="usd"))
        + card("Cost by cost centre", "KPI-COST-003",
               bar_chart([(r["K"], float(r["V"] or 0)) for r in cc], unit="usd",
                         classes=["warn" if r["K"] == "UNALLOCATED" else "" for r in cc]))
        + card("Serverless & AI credits", "KPI-COST-008",
               bar_chart([(r["K"], float(r["V"] or 0)) for r in sl], unit="credits", classes=["alt"] * len(sl)))
        + card("Costliest query signatures", "KPI-COST-006",
               table(["Signature", "Cost"], [[esc(r["K"]), esc(fmt(float(r["V"] or 0), "usd"))] for r in sig], {1}))
    )
    if value_summary and value_summary.get("items"):
        body += card("Suggestion-to-value", "Section 7.12 · identified vs realised", table(
            ["Suggestion", "Check", "Status", "Identified", "Realised"],
            [[esc(i["id"]), esc(i.get("check_id") or ""), esc(i.get("status") or ""),
              esc(fmt(i.get("identified_usd"), "usd")), esc(fmt(i.get("realised_usd"), "usd"))]
             for i in value_summary["items"]], {3, 4}))
    body += "</div>"
    return page("Executive Cost & Value", f"{account or 'All accounts'} · data as of {as_of}", body,
                f"Window {start}..{as_of}; spend reconciles to METERING_DAILY_HISTORY credits billed", theme)


def platform_health(db, as_of: date, account: str | None, theme: str | None, window_days: int) -> str:
    rs = default_rubrics()
    amber = float(rs.get(AMBER_REF))
    start = as_of - timedelta(days=window_days - 1)
    phi = _latest(db, "KPI_PHI_001", account, as_of)
    acc = " AND ACCOUNT_NAME = ?" if account else ""
    pillars = db.query(f"SELECT DIMENSION, avg(VALUE) AS V FROM KPI.KPI_PHI_002 WHERE PERIOD = "
                       f"(SELECT max(PERIOD) FROM KPI.KPI_PHI_002 WHERE PERIOD <= ?{acc}){acc} GROUP BY 1 ORDER BY 1",
                       [as_of] + ([account] if account else []) * 2)
    rows, counts = [], defaultdict(int)
    accounts = [account] if account else [r["ACCOUNT_NAME"] for r in db.query(
        "SELECT DISTINCT ACCOUNT_NAME FROM SEMANTIC.KPI_VALUES ORDER BY 1")]
    for k in sorted(implemented(engine="sql"), key=lambda k: (k.get("waf_pillar") or "", k["id"])):
        if not k.get("target_ref"):
            continue
        target = kpi_target(k, rs)
        for a in accounts:
            series = daily_series(db, k, a, start, as_of)
            agg = k.get("aggregation", "avg")
            v = window_value(series, "latest" if agg == "latest" else "avg", start, as_of)
            state = rag(v, target, k.get("direction", ""), amber)
            counts[state] += 1
            rows.append([esc(k["id"]), esc(k["name"]), esc(a), esc(k.get("waf_pillar", "")),
                         esc(fmt(v, k.get("unit"))), esc(fmt(target, k.get("unit"))),
                         f'<span class="rag {state}">{state}</span>'])
    alerts = db.query("SELECT ALERT_CLASS, SEVERITY, count(*) AS N FROM OPS.ALERT_EVENT WHERE STATUS = 'fired' "
                      "AND EVALUATED_FOR BETWEEN ? AND ? GROUP BY 1, 2 ORDER BY N DESC, 1", [start, as_of])
    tiles = [
        tile("{{HEALTH_INDEX_NAME}}", fmt(phi["VALUE"] if phi else None), f"observed · {phi['PERIOD'] if phi else '–'}"
             " · KPI-PHI-001"),
        tile("KPIs on target", str(counts["green"]), "green"),
        tile("KPIs near target", str(counts["amber"]), "amber", "warn" if counts["amber"] else ""),
        tile("KPIs off target", str(counts["red"]), "red", "bad" if counts["red"] else ""),
        tile("Alerts fired", str(sum(int(r["N"]) for r in alerts)), f"last {window_days} days"),
    ]
    body = (
        f'<div class="tiles">{"".join(tiles)}</div><div class="grid">'
        + card("Health Index by WAF pillar", "KPI-PHI-002",
               bar_chart([(r["DIMENSION"].replace("_", " "), float(r["V"] or 0)) for r in pillars], unit="score",
                                  classes=[_pillar_class(float(r["V"] or 0), rs) for r in pillars]))
        + card("Health Index trend", "KPI-PHI-001", line_chart(
            [(r["PERIOD"].strftime("%Y-%m"), float(r["VALUE"])) for r in db.query(
                f"SELECT PERIOD, avg(VALUE) AS VALUE FROM KPI.KPI_PHI_001 WHERE PERIOD <= ?{acc} GROUP BY 1 ORDER BY 1",
                [as_of] + ([account] if account else []))], unit="score"))
        + card("Alerts by class", "OPS.ALERT_EVENT", table(
            ["Class", "Severity", "Fired"], [[esc(r["ALERT_CLASS"]), esc(r["SEVERITY"]), esc(r["N"])] for r in alerts], {2}))
        + "</div>"
        + card("KPI attainment vs rubric targets", f"window {start}..{as_of}", table(
            ["KPI", "Name", "Account", "Pillar", "Value", "Target", "Status"], rows, {4, 5}))
    )
    return page("Platform Health", f"{account or 'All accounts'} · data as of {as_of}", body,
                "Targets and RAG bands come from rubric.obs.kpi_targets", theme)


def pipelines_freshness(db, as_of: date, account: str | None, theme: str | None, window_days: int) -> str:
    start = as_of - timedelta(days=window_days - 1)
    acc = " AND ACCOUNT_NAME = ?" if account else ""
    ap = [account] if account else []
    sr = db.query(f"SELECT PERIOD, avg(VALUE) AS V FROM KPI.KPI_REL_001 WHERE PERIOD BETWEEN ? AND ?{acc} "
                  "GROUP BY 1 ORDER BY 1", [start, as_of] + ap)
    fresh = db.query(f"SELECT DIMENSION, avg(VALUE) AS V FROM KPI.KPI_REL_003 WHERE PERIOD BETWEEN ? AND ?{acc} "
                     "GROUP BY 1 ORDER BY 1", [start, as_of] + ap)
    failed = db.query(f"SELECT ACCOUNT_NAME, FQ_NAME, SCHEDULED_TIME, IS_TIER1, ERROR_MESSAGE FROM CURATED.FACT_TASK_RUN "
                      f"WHERE STATE = 'FAILED' AND DAY BETWEEN ? AND ?{acc} ORDER BY SCHEDULED_TIME DESC LIMIT 15",
                      [as_of - timedelta(days=6), as_of] + ap)
    failed_24h = db.scalar(f"SELECT coalesce(sum(VALUE), 0) FROM KPI.KPI_REL_002 WHERE PERIOD = ?{acc}", [as_of] + ap)
    harvest = [f for f in freshness(db, as_of) if not account or f["account"] == account]
    late = [f for f in harvest if not f["met"]]
    rs = default_rubrics()
    attain_target = float(rs.get("rubric.obs.kpi_targets.freshness_attainment_min"))
    avg_sr = sum(float(r["V"]) for r in sr) / len(sr) if sr else None
    avg_fresh = sum(float(r["V"]) for r in fresh) / len(fresh) if fresh else None
    tiles = [
        tile("Task success rate", fmt(avg_sr, "ratio"), f"last {window_days} days · KPI-REL-001"),
        tile("Failed tasks (24h)", fmt(failed_24h), f"{as_of} · KPI-REL-002", "bad" if failed_24h else ""),
        tile("Freshness SLA attainment", fmt(avg_fresh, "ratio"), "Tier-1 tables · KPI-REL-003",
             "warn" if avg_fresh is not None and avg_fresh < attain_target else ""),
        tile("Harvest sources late", str(len(late)), f"of {len(harvest)} vs freshness SLAs", "warn" if late else ""),
    ]
    body = (
        f'<div class="tiles">{"".join(tiles)}</div><div class="grid">'
        + card("Task success rate", "KPI-REL-001", line_chart(
            [(r["PERIOD"].strftime("%m-%d"), float(r["V"])) for r in sr], unit="ratio",
            target=float(rs.get("rubric.obs.kpi_targets.task_success_min"))))
        + card("Freshness SLA attainment by table", "KPI-REL-003", bar_chart(
            [(r["DIMENSION"], float(r["V"])) for r in fresh], unit="ratio",
            classes=["alt" if float(r["V"]) >= attain_target else "bad" for r in fresh]))
        + card("Failed task runs (last 7 days)", "CURATED.FACT_TASK_RUN", table(
            ["Account", "Task", "Scheduled", "Tier-1", "Error"],
            [[esc(r["ACCOUNT_NAME"]), esc(r["FQ_NAME"]), esc(r["SCHEDULED_TIME"]), "yes" if r["IS_TIER1"] else "no",
              esc((r["ERROR_MESSAGE"] or "")[:80])] for r in failed]))
        + card("Observability harvest freshness", "RAW.HARVEST_LOG vs rubric.obs.freshness", table(
            ["Account", "Source", "Domain", "Lag (h)", "SLA (h)", "Status"],
            [[esc(f["account"]), esc(f["source"]), esc(f["domain"]),
              esc("–" if f["lag_hours"] is None else f"{f['lag_hours']:.1f}"), esc(f"{f['sla_hours']:g}"),
              f'<span class="rag {"green" if f["met"] else "red"}">{"on time" if f["met"] else "late"}</span>']
             for f in sorted(harvest, key=lambda f: (f["met"], f["account"], f["source"]))], {3, 4}))
        + "</div>"
    )
    return page("Pipelines & Freshness", f"{account or 'All accounts'} · data as of {as_of}", body,
                f"Window {start}..{as_of}", theme)


# --------------------------------------------------------------------------- chargeback


def chargeback_statements(db: ObsDatabase, month: date, registry: dict | None, theme: str | None) -> dict[str, str]:
    """One statement per cost centre for ``month`` (+ an index). Sums reconcile to KPI-COST-011 for the month."""
    month = month.replace(day=1)
    end = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    reg = registry or {}
    owners = (reg.get("cost_centres") or {}).get("owners") or {}
    price = {r["ACCOUNT_NAME"]: r["PRICE_PER_CREDIT"] for r in db.query("SELECT * FROM CURATED.DIM_ACCOUNT")}
    lines = db.query(
        "SELECT ACCOUNT_NAME, coalesce(COST_CENTRE, 'UNALLOCATED') AS CC, WAREHOUSE_NAME AS ITEM, 'Warehouse compute' AS KIND, "
        "sum(CREDITS_BILLED) AS CREDITS FROM CURATED.FACT_WAREHOUSE_DAILY WHERE DAY BETWEEN ? AND ? GROUP BY 1, 2, 3 "
        "UNION ALL SELECT ACCOUNT_NAME, 'UNALLOCATED', SERVICE_TYPE, 'Serverless / AI', sum(CREDITS_BILLED) "
        "FROM CURATED.FACT_METERING_DAILY WHERE SERVICE_TYPE <> 'WAREHOUSE_METERING' AND DAY BETWEEN ? AND ? "
        "GROUP BY 1, 2, 3 ORDER BY 2, 1, 4, 3", [month, end, month, end])
    billed = float(db.scalar("SELECT coalesce(sum(VALUE), 0) FROM KPI.KPI_COST_011 WHERE PERIOD BETWEEN ? AND ?",
                             [month, end]) or 0.0)
    by_cc: dict[str, list[dict]] = defaultdict(list)
    for r in lines:
        by_cc[r["CC"]].append({**r, "USD": float(r["CREDITS"] or 0) * float(price.get(r["ACCOUNT_NAME"]) or 0)})
    out: dict[str, str] = {}
    index_rows = []
    tpl = (TEMPLATES / "chargeback.html").read_text()
    for cc in sorted(by_cc):
        items = by_cc[cc]
        total = sum(i["USD"] for i in items)
        credits = sum(float(i["CREDITS"] or 0) for i in items)
        sid = stable_id("CHB", cc, month.isoformat(), round(total, 2))
        table_html = table(["Account", "Item", "Type", "Credits", "Charge"],
                           [[esc(i["ACCOUNT_NAME"]), esc(i["ITEM"]), esc(i["KIND"]), esc(f"{float(i['CREDITS'] or 0):,.2f}"),
                             esc(fmt(i["USD"], "usd"))] for i in items], {3, 4},
                           total=["Total", "", "", esc(f"{credits:,.2f}"), esc(fmt(total, "usd"))])
        accts = sorted({i["ACCOUNT_NAME"] for i in items})
        doc = render(tpl, theme, COST_CENTRE=esc(cc), MONTH=f"{month:%B %Y}", STATEMENT_ID=sid,
                     ACCOUNTS=esc(", ".join(accts)), OWNER=esc(owners.get(cc, "unassigned")),
                     PRICE=esc(", ".join(f"{a}: ${float(price.get(a) or 0):,.2f}/credit" for a in accts)),
                     TOTAL=esc(fmt(total, "usd")), SHARE=esc(fmt(total / billed if billed else None, "ratio")),
                     LINES=table_html,
                     NOTE=esc("Warehouse charges use credits billed (compute + cloud services, net of the daily "
                              "cloud-services adjustment) attributed by the warehouse's cost-centre tag. Serverless, AI "
                              "and untagged spend is UNALLOCATED. All statements for the month sum to the billed total."))
        fname = f"chargeback/{month:%Y-%m}_{cc.lower()}.html"
        out[fname] = doc
        index_rows.append([f'<a href="{esc(Path(fname).name)}">{esc(cc)}</a>', esc(owners.get(cc, "unassigned")),
                           esc(f"{credits:,.2f}"), esc(fmt(total, "usd")),
                           esc(fmt(total / billed if billed else None, "ratio"))])
    grand = sum(sum(i["USD"] for i in v) for v in by_cc.values())
    body = card(f"Chargeback statements — {month:%B %Y}", "KPI-COST-003 · reconciles to KPI-COST-011", table(
        ["Cost centre", "Owner", "Credits", "Charge", "Share"], index_rows, {2, 3, 4},
        total=["Total", "", "", esc(fmt(grand, "usd")), esc(fmt(grand / billed if billed else None, "ratio"))]))
    body += f'<p class="empty">Billed spend for the month (KPI-COST-011): {esc(fmt(billed, "usd"))}.</p>'
    out["chargeback/index.html"] = page("Chargeback statements", f"{month:%B %Y}", body,
                                        "Dashboard 8 — monthly, per cost centre, exportable", theme, depth=1)
    return out


def render_dashboards(db: ObsDatabase, out_dir: str | Path, *, as_of: date | None = None, account: str | None = None,
                      theme: str | None = None, registry: dict | str | None = None, window_days: int | None = None,
                      value_summary: dict | None = None, rubrics: RubricSet | None = None) -> list[str]:
    """Render dashboards 1, 2, 4 and the chargeback statements for the latest complete month into ``out_dir``."""
    rubrics = rubrics or default_rubrics()
    reg = registry if isinstance(registry, dict) else load_registry(registry)
    as_of = as_of or db.scalar("SELECT max(PERIOD) FROM KPI.KPI_COST_011")
    if as_of is None:
        raise ValueError("no KPI data: run `altitude obs kpis` first")
    window_days = window_days or int(rubrics.get("rubric.obs.value.after_days")) * 2
    docs = {
        "executive_cost_value.html": executive_cost_value(db, as_of, account, theme, window_days, value_summary),
        "platform_health.html": platform_health(db, as_of, account, theme, window_days),
        "pipelines_freshness.html": pipelines_freshness(db, as_of, account, theme, window_days),
    }
    month = as_of.replace(day=1)
    last_month_end = month - timedelta(days=1)
    statement_month = month if (as_of + timedelta(days=1)).day == 1 else last_month_end.replace(day=1)
    if not db.scalar("SELECT count(*) FROM KPI.KPI_COST_011 WHERE PERIOD BETWEEN ? AND ?",
                     [statement_month, statement_month + timedelta(days=27)]):
        statement_month = month
    docs.update(chargeback_statements(db, statement_month, reg, theme))
    out = Path(out_dir)
    written = []
    for rel, text in sorted(docs.items()):
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        written.append(str(p))
    return written
