"""Deliverables generated from one sealed snapshot (Section 6.9).

Every artifact carries ``snapshot_id`` + ``rubric_version`` (and the catalogue hash). CSV and JSON outputs are
byte-identical for the same snapshot + rubric version (sorted keys, fixed line endings, no wall clock).
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from altitude.core import theme as theme_mod
from altitude.core.generated import stamp

from .engine import DiagnosticResult, json_safe

ALL_FORMATS = ["suggestions_json", "evidence_json", "findings_csv", "findings_xlsx", "jira_csv", "ado_csv", "pr_pack",
               "report_html", "deck_pptx", "savings_xlsx"]

FILENAMES = {
    "suggestions_json": "suggestions.json",
    "evidence_json": "evidence.json",
    "findings_csv": "findings_register.csv",
    "findings_xlsx": "findings_register.xlsx",
    "jira_csv": "backlog_jira.csv",
    "ado_csv": "backlog_azure_devops.csv",
    "pr_pack": "remediation_pr_pack",
    "report_html": "diagnostic_report.html",
    "deck_pptx": "executive_readout.pptx",
    "savings_xlsx": "savings_risk_model.xlsx",
}

FINDINGS_COLUMNS = [
    "rank", "suggestion_id", "check_id", "domain", "waf_pillar", "severity", "title", "affected_objects",
    "evidence_refs", "value_p50_usd", "value_conservative_usd", "value_method", "risk_likelihood", "risk_impact",
    "risk_score", "risk_residual_score", "effort_size", "effort_hours_p50", "confidence", "review",
    "rationale", "quadrant", "remediation_type", "autonomy", "artifact_ref", "rollback_ref", "kpis_to_watch",
    "status", "reviewer", "snapshot_id", "rubric_version",
]


# --------------------------------------------------------------------------- helpers


def _csv(rows: Iterable[Iterable[Any]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    for r in rows:
        w.writerow(["" if v is None else v for v in r])
    return buf.getvalue()


def _json(obj: Any) -> str:
    return json.dumps(json_safe(obj), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _sealed_dt(result: DiagnosticResult) -> datetime:
    try:
        return datetime.fromisoformat(result.context.sealed_at).replace(tzinfo=None)
    except (TypeError, ValueError):
        return datetime(result.context.window_end.year, result.context.window_end.month, result.context.window_end.day)


def records(result: DiagnosticResult, statuses: list[dict] | None = None) -> list[dict]:
    return statuses if statuses is not None else result.suggestions


def finding_rows(result: DiagnosticResult, recs: list[dict] | None = None) -> list[dict]:
    recs = records(result, recs)
    out = []
    for s in recs:
        d = result.detail(s["id"])
        v = s["value"]["annualised_usd"] or {}
        r = s["risk_reduction"] or {}
        out.append({
            "rank": s["priority"]["rank"], "suggestion_id": s["id"], "check_id": s["check_id"], "domain": s["domain"],
            "waf_pillar": s["waf_pillar"], "severity": d.severity, "title": s["title"],
            "affected_objects": "; ".join(s["affected_objects"]), "evidence_refs": "; ".join(s["evidence_refs"]),
            "value_p50_usd": v.get("p50"), "value_conservative_usd": v.get("conservative"),
            "value_method": s["value"]["method"], "risk_likelihood": r.get("likelihood"), "risk_impact": r.get("impact"),
            "risk_score": r.get("score"), "risk_residual_score": r.get("residual_score"),
            "effort_size": s["effort"]["size"], "effort_hours_p50": s["effort"]["hours_p50"],
            "confidence": f"{s['confidence']:.3f}", "review": d.review_reason or "",
            "rationale": s["rationale"], "quadrant": s["priority"]["quadrant"], "remediation_type": s["remediation"]["type"],
            "autonomy": s["remediation"]["autonomy"], "artifact_ref": s["remediation"]["artifact_ref"],
            "rollback_ref": s["remediation"]["rollback_ref"], "kpis_to_watch": "; ".join(s["kpis_to_watch"]),
            "status": s["status"], "reviewer": s["reviewer"] or "", "snapshot_id": s["snapshot_id"],
            "rubric_version": result.rubric_version,
        })
    return out


# --------------------------------------------------------------------------- text exports


def suggestions_json(result: DiagnosticResult, recs: list[dict] | None = None) -> str:
    recs = records(result, recs)
    return _json({
        **result.stamp,
        "schema": "altitude.diagnostics.suggestion/1.0",
        "kpi_ids": sorted({k for s in recs for k in s["kpis_to_watch"]}),
        "platform_health_index": result.scorecard["platform_health_index"],
        "suggestions": recs,
    })


def evidence_json(result: DiagnosticResult) -> str:
    return _json({**result.stamp, "evidence": result.evidence})


def findings_csv(result: DiagnosticResult, recs: list[dict] | None = None) -> str:
    rows = finding_rows(result, recs)
    return _csv([FINDINGS_COLUMNS] + [[r[c] for c in FINDINGS_COLUMNS] for r in rows])


_JIRA_PRIORITY = {"quick_win": "High", "strategic": "High", "hygiene": "Medium", "defer": "Low"}
_ADO_PRIORITY = {"quick_win": 1, "strategic": 2, "hygiene": 3, "defer": 4}


def _ticket_description(result: DiagnosticResult, s: dict) -> str:
    v = s["value"]["annualised_usd"]
    r = s["risk_reduction"]
    value_txt = "${:,} p50 / ${:,} conservative per year".format(v["p50"], v["conservative"]) if v else "n/a"
    risk_txt = ("score {} (L{} x I{}) -> {}".format(r["score"], r["likelihood"], r["impact"], r["residual_score"])
                if r else "n/a")
    lines = [
        s["rationale"],
        "",
        f"Value: {value_txt} (method: {s['value']['method']})",
        f"Risk: {risk_txt}",
        f"Effort: {s['effort']['size']} (~{s['effort']['hours_p50']:g} h); confidence {s['confidence']:.2f}",
        f"Affected objects: {', '.join(s['affected_objects'])}",
        f"Evidence: {', '.join(s['evidence_refs'])}",
        f"Remediation: {s['remediation']['artifact_ref']} (rollback {s['remediation']['rollback_ref']}, autonomy {s['remediation']['autonomy']})",
        f"KPIs to watch: {', '.join(s['kpis_to_watch'])}",
        f"Snapshot: {result.snapshot_id} | Rubric: {result.rubric_version} | Suggestion: {s['id']}",
    ]
    return "\n".join(lines)


def jira_csv(result: DiagnosticResult, recs: list[dict] | None = None) -> str:
    header = ["Issue Type", "Summary", "Description", "Priority", "Labels", "Labels", "Labels", "Labels",
              "Original Estimate", "Component/s", "External ID"]
    rows = [header]
    for s in records(result, recs):
        d = result.detail(s["id"])
        prio = "Highest" if d.severity == "critical" else _JIRA_PRIORITY[s["priority"]["quadrant"]]
        rows.append(["Task", f"[{s['check_id']}] {s['title']}", _ticket_description(result, s), prio,
                     "altitude-diagnostics", s["domain"], s["priority"]["quadrant"], f"snapshot-{result.snapshot_id}",
                     int(round(float(s["effort"]["hours_p50"]) * 3600)), s["waf_pillar"], s["id"]])
    return _csv(rows)


def ado_csv(result: DiagnosticResult, recs: list[dict] | None = None) -> str:
    rows = [["Work Item Type", "Title", "Description", "Priority", "Tags", "Original Estimate", "Area Path"]]
    for s in records(result, recs):
        d = result.detail(s["id"])
        prio = 1 if d.severity == "critical" else _ADO_PRIORITY[s["priority"]["quadrant"]]
        tags = "; ".join(["altitude-diagnostics", s["check_id"], s["domain"], s["priority"]["quadrant"],
                          f"snapshot-{result.snapshot_id}", f"rubric-{result.rubric_version}"])
        rows.append(["Task", f"[{s['check_id']}] {s['title']}", _ticket_description(result, s).replace("\n", "<br/>"),
                     prio, tags, f"{float(s['effort']['hours_p50']):g}", s["waf_pillar"]])
    return _csv(rows)


def pr_pack(result: DiagnosticResult, recs: list[dict] | None = None, theme: str | None = None) -> dict[str, str]:
    """Remediation-as-code pull-request pack: stamped forward + rollback per suggestion, manifest, README."""
    files: dict[str, str] = {}
    manifest = []
    for s in records(result, recs):
        d = result.detail(s["id"])
        files.update(d.artifacts)
        manifest.append({"suggestion_id": s["id"], "check_id": s["check_id"], "title": s["title"],
                         "type": s["remediation"]["type"], "autonomy": s["remediation"]["autonomy"],
                         "artifact_ref": s["remediation"]["artifact_ref"], "rollback_ref": s["remediation"]["rollback_ref"],
                         "confidence": s["confidence"], "review": d.review_reason, "status": s["status"]})
    body = json.dumps({**result.stamp, "artifacts": manifest}, indent=2, sort_keys=True)
    files["manifest.json"] = stamp(body, ".json", f"diagnostics snapshot {result.snapshot_id}")
    name = theme_mod.token("PRODUCT_NAME", theme)
    pkg = theme_mod.token("PACKAGE_D_NAME", theme)
    lines = [
        f"# {pkg}: remediation-as-code pack",
        "",
        f"Generated by {name} from sealed snapshot `{result.snapshot_id}` with rubric `{result.rubric_version}` "
        f"(catalogue `{result.catalogue_hash}`).",
        "",
        "Every change is a draft for human approval: nothing here runs automatically. Each forward script has a",
        "matching rollback (`*.rollback.*`); run the rollback if a KPI listed for the suggestion regresses.",
        "",
        "| Rank | Suggestion | Check | Type | Autonomy | Forward | Rollback |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in records(result, recs):
        rem = s["remediation"]
        lines.append(f"| {s['priority']['rank']} | {s['id']}: {s['title']} | {s['check_id']} | {rem['type']} | "
                     f"{rem['autonomy']} | `{rem['artifact_ref']}` | `{rem['rollback_ref']}` |")
    lines += ["", "Suggestions below the confidence floor stay in the review queue until a named reviewer approves them."]
    files["README.md"] = stamp("\n".join(lines) + "\n", ".md", f"diagnostics snapshot {result.snapshot_id}")
    return files


# --------------------------------------------------------------------------- spreadsheets


def _workbook(result: DiagnosticResult):
    from openpyxl import Workbook

    wb = Workbook()
    dt = _sealed_dt(result)
    wb.properties.creator = "diagnostics"
    wb.properties.created = dt
    wb.properties.modified = dt
    wb.properties.title = f"{result.snapshot_id} {result.rubric_version}"
    return wb


def _sheet(wb, title: str, header: list[str], rows: Iterable[Iterable[Any]], first: bool = False):
    from openpyxl.styles import Font, PatternFill

    ws = wb.active if first else wb.create_sheet()
    ws.title = title
    ws.append(header)
    fill = PatternFill("solid", fgColor=theme_mod.token("COLOR_PRIMARY").lstrip("#"))
    for cell in ws[1]:
        cell.font = Font(bold=True, color=theme_mod.token("COLOR_SURFACE").lstrip("#"))
        cell.fill = fill
    for r in rows:
        ws.append(list(r))
    ws.freeze_panes = "A2"
    return ws


def _about(wb, result: DiagnosticResult) -> None:
    rows = [("snapshot_id", result.snapshot_id), ("rubric_version", result.rubric_version),
            ("catalogue_hash", result.catalogue_hash), ("tier", result.tier),
            ("window", f"{result.context.window_start.date()} .. {result.context.window_end.date()}"),
            ("platform_health_index", result.scorecard["platform_health_index"])]
    _sheet(wb, "About", ["key", "value"], rows)


def findings_xlsx(result: DiagnosticResult, path: Path, recs: list[dict] | None = None) -> None:
    wb = _workbook(result)
    rows = finding_rows(result, recs)
    _sheet(wb, "Findings", FINDINGS_COLUMNS, ([r[c] for c in FINDINGS_COLUMNS] for r in rows), first=True)
    ev_cols = ["id", "check_id", "object", "kind", "cluster_key", "metrics", "source_tables", "detector_ref", "detector_sha"]
    _sheet(wb, "Evidence", ev_cols, ([e["id"], e["check_id"], e["object"], e["kind"], e["cluster_key"],
                                      json.dumps(e["metrics"], sort_keys=True), ", ".join(e["source_tables"]),
                                      e["detector_ref"], e["detector_sha"]] for e in result.evidence))
    sc = result.scorecard
    _sheet(wb, "Scorecard", ["scope", "key", "name", "score_1_5", "label", "raw_0_1", "checks_evaluated", "checks_failed"],
           [("domain", d["id"], d["name"], d["score"], d["label"], d["raw"], d["checks_evaluated"], d["checks_failed"])
            for d in sc["domains"]]
           + [("pillar", p["pillar"], p["name"], p["score"], p["label"], p["raw"], p["checks_evaluated"], p["checks_failed"])
              for p in sc["pillars"]]
           + [("index", "PHI", "Platform Health Index", None, None, sc["platform_health_index"], None, None)])
    _about(wb, result)
    wb.save(path)


def savings_xlsx(result: DiagnosticResult, path: Path, recs: list[dict] | None = None) -> None:
    """Savings & risk model with explicit assumptions (contract price is an input)."""
    wb = _workbook(result)
    _sheet(wb, "Assumptions", ["assumption", "value", "unit", "source"],
           ([a["name"], a["value"] if not isinstance(a["value"], (dict, list)) else json.dumps(a["value"]), a["unit"],
             a["source"]] for a in result.assumptions), first=True)
    recs = records(result, recs)
    srows = []
    for s in recs:
        v = s["value"]["annualised_usd"]
        if not v:
            continue
        d = result.detail(s["id"])
        for vr in d.value_rows:
            srows.append([s["id"], s["check_id"], s["domain"], s["title"], vr["object"], vr["p50"], vr["conservative"],
                          s["value"]["method"], s["priority"]["quadrant"], s["confidence"]])
    ws = _sheet(wb, "Savings", ["suggestion_id", "check_id", "domain", "title", "object", "annual_usd_p50",
                                "annual_usd_conservative", "method", "quadrant", "confidence"], srows)
    n = len(srows) + 1
    _sheet(wb, "Risk", ["suggestion_id", "check_id", "domain", "title", "likelihood_1_5", "impact_1_5", "score",
                        "residual_score", "method"],
           ([s["id"], s["check_id"], s["domain"], s["title"], s["risk_reduction"]["likelihood"],
             s["risk_reduction"]["impact"], s["risk_reduction"]["score"], s["risk_reduction"]["residual_score"],
             s["risk_reduction"]["method"]] for s in recs if s["risk_reduction"]))
    summary = _sheet(wb, "Summary", ["domain", "annual_usd_p50", "annual_usd_conservative"], [])
    domains = sorted({r[2] for r in srows}, key=lambda x: int(x[1:]))
    for i, dom in enumerate(domains, start=2):
        summary.append([dom, f'=SUMIF(Savings!C2:C{n},A{i},Savings!F2:F{n})',
                        f'=SUMIF(Savings!C2:C{n},A{i},Savings!G2:G{n})'])
    last = len(domains) + 1
    summary.append(["TOTAL", f"=SUM(B2:B{last})", f"=SUM(C2:C{last})"])
    summary.append([])
    summary.append(["Note", "Values of overlapping suggestions (e.g. idle time and downsizing on one warehouse) are not "
                            "strictly additive; the conservative column applies each check's rubric haircut."])
    _about(wb, result)
    wb.save(path)


# --------------------------------------------------------------------------- orchestration


def export_all(result: DiagnosticResult, out_dir: str | Path, formats: list[str] | None = None,
               recs: list[dict] | None = None, theme: str | None = None) -> dict[str, Path]:
    """Write every requested deliverable (default: the tier's export list) under ``out_dir``."""
    from .deck import build_deck
    from .report import render_report

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if formats is None:
        from .catalogue import default_catalogue

        formats = list(default_catalogue().tier(result.tier)["exports"])
    unknown = set(formats) - set(ALL_FORMATS)
    if unknown:
        raise ValueError(f"unknown export format(s): {sorted(unknown)}")
    written: dict[str, Path] = {}
    text: dict[str, Callable[[], str]] = {
        "suggestions_json": lambda: suggestions_json(result, recs),
        "evidence_json": lambda: evidence_json(result),
        "findings_csv": lambda: findings_csv(result, recs),
        "jira_csv": lambda: jira_csv(result, recs),
        "ado_csv": lambda: ado_csv(result, recs),
        "report_html": lambda: render_report(result, recs, theme=theme),
    }
    for fmt in formats:
        path = out / FILENAMES[fmt]
        if fmt in text:
            path.write_text(text[fmt](), encoding="utf-8")
        elif fmt == "pr_pack":
            for rel, content in sorted(pr_pack(result, recs, theme=theme).items()):
                p = path / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding="utf-8")
        elif fmt == "findings_xlsx":
            findings_xlsx(result, path, recs)
        elif fmt == "savings_xlsx":
            savings_xlsx(result, path, recs)
        elif fmt == "deck_pptx":
            build_deck(result, path, recs, theme=theme)
        written[fmt] = path
    return written
