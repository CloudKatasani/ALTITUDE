"""Assessment report export: Markdown, HTML and CSV inventory from a sealed assessment snapshot.

Templates live in ``templates/`` and use ``{{TOKEN}}`` theme placeholders only
(white-label, principle 8); data placeholders are lower-case Jinja variables.
Outputs contain no wall-clock values, so the same snapshot and theme always
produce byte-identical files.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

import jinja2

from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.snapshot import Snapshot
from altitude.core.theme import render as theme_render

from .engine import AssessmentResult, load_assessment

TEMPLATES = Path(__file__).parent / "templates"
INVENTORY_COLUMNS = ["object_id", "fq_name", "object_type", "loc", "usage_90d", "last_used_at", "disposition",
                     "confidence", "needs_review", "complexity_score", "complexity_band", "anti_pattern_hits",
                     "credits_month", "drift_hits", "rule", "rationale"]


def _context(result: AssessmentResult, rubrics: RubricSet) -> dict[str, Any]:
    inv = sorted(result.rows("object_assessment"), key=lambda r: r["fq_name"])
    top_n = int(rubrics.get("rubric.assessment.report.top_n"))
    hits = sorted(result.rows("anti_pattern_hit"), key=lambda h: (-float(h["credits_month"]), h["hit_id"]))
    return {
        "s": result.summary,
        "snapshot_id": result.snapshot_id,
        "review": [r for r in inv if r["needs_review"]],
        "retire": [r for r in inv if r["disposition"] == "retire" and not r["needs_review"]],
        "rewrite": [r for r in inv if r["disposition"] == "rewrite"],
        "hits": hits[:top_n],
        "drift": sorted(result.rows("drift_hit"), key=lambda d: (d["severity"], d["issue_id"], d["fq_name"])),
    }


def render(result: AssessmentResult, fmt: str, theme: str | None = None, rubrics: RubricSet | None = None) -> str:
    if fmt == "csv":
        return inventory_csv(result)
    name = {"md": "report.md.j2", "html": "report.html.j2"}[fmt]
    themed = theme_render((TEMPLATES / name).read_text(), theme)
    env = jinja2.Environment(autoescape=fmt == "html", keep_trailing_newline=True, undefined=jinja2.StrictUndefined)
    return env.from_string(themed).render(**_context(result, rubrics or default_rubrics()))


def inventory_csv(result: AssessmentResult) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=INVENTORY_COLUMNS, lineterminator="\n", extrasaction="ignore")
    w.writeheader()
    for r in sorted(result.rows("object_assessment"), key=lambda r: r["fq_name"]):
        row = dict(r)
        row["last_used_at"] = row["last_used_at"].isoformat() if row.get("last_used_at") else ""
        w.writerow(row)
    return buf.getvalue()


def export_report(source: AssessmentResult | Snapshot | str | Path, out_dir: str | Path, *, theme: str | None = None,
                  rubrics: RubricSet | None = None) -> dict[str, Path]:
    # always render from the sealed snapshot, never from in-memory state
    result = load_assessment(source.snapshot if isinstance(source, AssessmentResult) else source)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for fmt, fname in (("md", "assessment_report.md"), ("html", "assessment_report.html"), ("csv", "inventory.csv")):
        p = out / fname
        p.write_text(render(result, fmt, theme, rubrics))
        paths[fmt] = p
    return paths
