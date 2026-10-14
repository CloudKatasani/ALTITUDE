"""Diagnostic report (HTML): findings by domain, method, assumptions and evidence appendix.

The page skeleton is ``templates/report.html`` and uses ``{{TOKEN}}`` placeholders only (white-label: names
and colours come from theme tokens via :func:`altitude.core.theme.render`). Content blocks are escaped HTML.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from altitude.core import theme as theme_mod

from .engine import DiagnosticResult

TEMPLATE = Path(__file__).parent / "templates" / "report.html"


def _e(v: object) -> str:
    return html.escape("" if v is None else str(v))


def _table(header: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _usd(v: float | int | None) -> str:
    return "—" if v is None else f"${v:,.0f}"


def render_report(result: DiagnosticResult, recs: list[dict] | None = None, theme: str | None = None) -> str:
    recs = recs if recs is not None else result.suggestions
    sc = result.scorecard
    total_p50 = sum((s["value"]["annualised_usd"] or {}).get("p50", 0) for s in recs)
    total_cons = sum((s["value"]["annualised_usd"] or {}).get("conservative", 0) for s in recs)
    quick = [s for s in recs if s["priority"]["quadrant"] == "quick_win"]
    review = [s for s in recs if result.detail(s["id"]).needs_review]
    phi = sc["platform_health_index"]
    kpis = [
        (f"{phi:.1f}" if phi is not None else "—", theme_mod.token("HEALTH_INDEX_NAME", theme)),
        (_usd(total_p50), "Identified value / yr (p50)"),
        (_usd(total_cons), "Conservative / yr"),
        (str(len(recs)), "Suggestions"),
        (str(len(quick)), "Quick wins"),
        (str(len(review)), "In review queue"),
    ]
    summary = '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="v">{_e(v)}</div><div class="l">{_e(label)}</div></div>' for v, label in kpis
    ) + "</div>"
    top = recs[:3]
    if top:
        summary += "<p>Top priorities: " + "; ".join(f"<b>{_e(s['title'])}</b>" for s in top) + ".</p>"

    dom_rows = [[_e(d["id"]), _e(d["name"]), _e(d["waf_pillar"]),
                 f'<span class="score-{d["score"]}">{_e(d["score"])}</span> {_e(d["label"])}' if d["score"] else "not in scope",
                 _e(d["raw"]), _e(d["checks_evaluated"]), _e(d["checks_failed"])] for d in sc["domains"]]
    pil_rows = [[_e(p["name"]), f'<span class="score-{p["score"]}">{_e(p["score"])}</span> {_e(p["label"])}' if p["score"] else "—",
                 _e(p["index"])] for p in sc["pillars"]]
    scorecard = (f"<p>{_e(theme_mod.token('HEALTH_INDEX_NAME', theme))}: <b>{_e(phi)}</b> / 100</p>"
                 + _table(["Domain", "Name", "WAF pillar", "Score (1–5)", "Raw", "Checks evaluated", "Checks failing"], dom_rows)
                 + "<h3>Well-Architected pillar roll-up</h3>"
                 + _table(["Pillar", "Score (1–5)", "Index (0–100)"], pil_rows))

    recs_html = _table(["Pattern", "Recommended next package", "Evidence"],
                       [[_e(r["pattern"]), _e(r["package"]), _e(", ".join(r["evidence"]))] for r in result.recommendations]) \
        if result.recommendations else "<p>No follow-on package indicated.</p>"

    findings = []
    for d in sorted({s["domain"] for s in recs}, key=lambda x: int(x[1:])):
        dom = next(x for x in sc["domains"] if x["id"] == d)
        findings.append(f"<h3>{_e(d)} {_e(dom['name'])}</h3>")
        for s in [x for x in recs if x["domain"] == d]:
            det = result.detail(s["id"])
            v = s["value"]["annualised_usd"]
            r = s["risk_reduction"]
            cls = "finding review" if det.needs_review else "finding"
            findings.append(
                f'<div class="{cls}"><b>#{s["priority"]["rank"]} {_e(s["title"])}</b> '
                f'<span class="tag">{_e(s["id"])}</span><span class="tag">{_e(s["check_id"])}</span>'
                f'<span class="tag">{_e(s["priority"]["quadrant"])}</span><span class="tag">{_e(det.severity)}</span>'
                f'<p>{_e(det.narrative)}</p>'
                f'<p><b>Value:</b> {_e(_usd(v["p50"]) + " p50 / " + _usd(v["conservative"]) + " conservative" if v else "n/a")} — '
                f'{_e(s["value"]["method"])}<br>'
                f'<b>Risk:</b> {_e("score %s → %s (%s)" % (r["score"], r["residual_score"], r["method"]) if r else "n/a")}<br>'
                f'<b>Effort:</b> {_e(s["effort"]["size"])} (~{_e(s["effort"]["hours_p50"])} h) · '
                f'<b>Confidence:</b> {s["confidence"]:.2f}{" (review required)" if det.needs_review else ""} · '
                f'<b>Status:</b> {_e(s["status"])}<br>'
                f'<b>Affected:</b> {_e(", ".join(s["affected_objects"]))}<br>'
                f'<b>Evidence:</b> {_e(", ".join(s["evidence_refs"]))}<br>'
                f'<b>Remediation:</b> <code>{_e(s["remediation"]["artifact_ref"])}</code> '
                f'(rollback <code>{_e(s["remediation"]["rollback_ref"])}</code>, autonomy {_e(s["remediation"]["autonomy"])}) · '
                f'<b>KPIs:</b> {_e(", ".join(s["kpis_to_watch"]))}</p></div>')
    findings_html = "".join(findings) or "<p>No findings.</p>"

    method = (
        "<p>Read-only, metadata-only harvest into an immutable, content-addressed snapshot; SQL detectors per check "
        "(stored as data) compute signals; rubric thresholds are bound by reference; findings are clustered by root cause "
        "(query signature, warehouse, dashboard, pipeline, owner); value is modelled from the contract price and measured "
        "credits (p50 and conservative, annualised) or as likelihood × impact where dollars do not apply; every suggestion "
        "carries a remediation draft with its rollback; confidence derives from evidence completeness, and suggestions "
        "below the review floor wait for a named reviewer.</p>"
        + _table(["Check", "Status", "Candidates", "Flagged", "Score"],
                 [[_e(c["check_id"] + " " + c["title"]), _e(c["status"]), _e(c["candidates"]), _e(c["flagged"]),
                   _e(c["score"])] for c in sc["checks"]]))
    assumptions = _table(["Assumption", "Value", "Unit", "Source"],
                         [[_e(a["name"]), _e(json.dumps(a["value"]) if isinstance(a["value"], (list, dict)) else a["value"]),
                           _e(a["unit"]), _e(a["source"])] for a in result.assumptions])
    refs = {r for s in recs for r in s["evidence_refs"]}
    evidence = _table(["Evidence", "Check", "Object", "Signals"],
                      [[_e(e["id"]), _e(e["check_id"]), _e(e["object"]),
                        f"<code>{_e(json.dumps(e['metrics'], sort_keys=True))}</code>"]
                       for e in result.evidence if e["id"] in refs])

    ctx = result.context
    template = TEMPLATE.read_text(encoding="utf-8")
    return theme_mod.render(
        template, theme,
        SNAPSHOT_ID=_e(result.snapshot_id), RUBRIC_VERSION=_e(result.rubric_version),
        CATALOGUE_HASH=_e(result.catalogue_hash), TIER=_e(result.tier),
        ACCOUNT_NAME=_e(ctx.account.get("ACCOUNT_NAME") or ctx.manifest.get("metadata", {}).get("account_name") or ""),
        WINDOW=_e(f"{ctx.window_start.date()} .. {ctx.window_end.date()}"),
        SUMMARY=summary, SCORECARD=scorecard, RECOMMENDATIONS=recs_html, FINDINGS=findings_html, METHOD=method,
        ASSUMPTIONS=assumptions, EVIDENCE=evidence,
    )
