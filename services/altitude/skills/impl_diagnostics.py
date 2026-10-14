"""Skill adapter for Package D diagnostics (``altitude.diagnostics``)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .context import coerce
from .impl_common import open_snapshot, out_dir, paths


def run_diagnostic(context: Any = None, snapshot_id: str = "", tier: str = "D2", formats: list | None = None,
                   tenant_id: str | None = None, engagement_id: str | None = None, theme: str | None = None) -> dict:
    """Run the suggestion engine on a sealed snapshot, persist the run and export the tier's deliverables."""
    from altitude.diagnostics import lifecycle
    from altitude.diagnostics.engine import DiagnosticsEngine
    from altitude.diagnostics.exports import export_all

    ctx = coerce(context)
    snap = open_snapshot(ctx, snapshot_id)
    result = DiagnosticsEngine(rubrics=ctx.rubrics).run(snap, tier=tier)
    run_id = lifecycle.persist(result, ctx.store, tenant_id=tenant_id, engagement_id=engagement_id,
                               rubrics=ctx.rubrics, snapshot=snap)
    recs = lifecycle.overlay_status(result, ctx.store)
    written = export_all(result, out_dir(ctx, "run_diagnostic", run_id), formats=formats, recs=recs, theme=theme)
    suggestions = result.suggestions
    return {
        **result.stamp,
        "run_id": run_id,
        "tier": tier,
        "platform_health_index": result.scorecard["platform_health_index"],
        "domains": {d["id"]: d["score"] for d in result.scorecard["domains"]},
        "suggestions": len(suggestions),
        "suggestions_by_check": dict(sorted(Counter(s["check_id"] for s in suggestions).items())),
        "in_review_queue": sum(1 for d in result.details if d.needs_review),
        "value_p50_usd": round(sum((s["value"]["annualised_usd"] or {}).get("p50", 0) for s in suggestions), 2),
        "top_suggestions": [{"suggestion_id": s["id"], "check_id": s["check_id"], "title": s["title"]}
                            for s in suggestions[:10]],
        "next_packages": [r["package"] for r in result.recommendations],
        "exports": paths(written),
    }
