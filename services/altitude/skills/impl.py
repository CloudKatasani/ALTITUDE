"""Skill implementations. Each takes ``context`` plus the manifest's arguments and returns JSON-able data."""

from __future__ import annotations

from typing import Any

from .context import coerce


def ask_sherpa(context: Any = None, question: str = "", facts: dict | None = None, advisor: str | None = None) -> dict:
    from altitude.advisory import Sherpa
    from altitude.api.app import default_grounding

    ctx = coerce(context)
    index = (ctx.extras.get("grounding") or default_grounding)(ctx)
    sherpa = Sherpa.advisor(advisor, index, store=ctx.store) if advisor else Sherpa(index, store=ctx.store)
    return sherpa.ask(question, facts or {}).to_dict()


def review_decision(context: Any = None, title: str = "", facts: dict | None = None,
                    evidence_refs: list | None = None, engagement_id: str | None = None) -> dict:
    from altitude.advisory import ReviewBoard

    ctx = coerce(context)
    return ReviewBoard(store=ctx.store).review(title, facts or {}, evidence_refs or [], engagement_id).to_dict()


def validate_knowledge(context: Any = None) -> dict:
    from altitude.core.knowledge import validate_tree

    problems = validate_tree()
    return {"ok": not problems, "problems": problems}


def build_synthetic_snapshot(context: Any = None, profile: str = "seeded", days: int = 90,
                             account_name: str = "ACME_PROD") -> dict:
    from altitude.synthetic import AccountSpec, build_snapshot

    ctx = coerce(context)
    spec = AccountSpec(profile=profile, days=days, account_name=account_name)
    sid = f"SNAP-{spec.organization}-{spec.end_date.isoformat()}-{profile.upper()}-{days}D"
    path = ctx.workspace / "snapshots" / f"{sid}.duckdb"
    if path.exists():
        from altitude.core.snapshot import Snapshot

        snap = Snapshot.open(path)
    else:
        snap, _ = build_snapshot(ctx.workspace / "snapshots", spec, snapshot_id=sid)
    snap.register(ctx.store)
    return {"snapshot_id": snap.snapshot_id, "path": str(snap.path), "content_hash": snap.content_hash,
            "tables": snap.tables()}


def build_go_no_go_pack(context: Any = None, engagement_id: str = "", plan_id: str = "", snapshot_id: str = "",
                        facts: dict | None = None) -> dict:
    from altitude.cutover import build_go_no_go_pack as build, render_markdown

    ctx = coerce(context)
    pack = build(ctx.store, engagement_id, plan_id, snapshot_id, facts or {})
    out = ctx.workspace / "cutover" / f"{pack['go_no_go_id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(pack))
    return {**pack, "report_path": str(out)}


def draft_sow(context: Any = None, offer_id: str = "", client: str = "", tier_id: str | None = None,
              scope_notes: list | None = None, fee_usd: float | None = None) -> dict:
    from altitude.commercial import draft_sow as draft

    return {"markdown": draft(offer_id, client, tier_id, scope_notes, fee_usd)}


def draft_business_case(context: Any = None, legacy_annual_costs: dict | None = None,
                        snowflake_annual_cost: float = 0.0, migration_cost: float = 0.0,
                        estimate: dict | None = None) -> dict:
    from altitude.commercial import draft_business_case as draft

    return draft(legacy_annual_costs or {}, snowflake_annual_cost, migration_cost, estimate)
