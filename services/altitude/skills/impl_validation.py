"""Skill adapters for the validation engine (``altitude.validation``)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

from .context import coerce
from .impl_common import out_dir, safe
from .registry import SkillError


def _spec(table: dict):
    from altitude.validation import TableSpec

    try:
        return TableSpec.from_dict(dict(table))
    except TypeError as e:
        raise SkillError(f"invalid table spec: {e}") from None


def generate_reconciliation_suite(context: Any = None, tables: list | None = None, persist: bool = True) -> dict:
    """Generate tiered L0-L5 reconciliation suites (checks + thresholds by tier) for one or more tables."""
    from altitude.validation import generate_suite, persist_suite

    ctx = coerce(context)
    if not tables:
        raise SkillError("at least one table spec is required")
    suites, docs = [], []
    for t in tables:
        try:
            s = generate_suite(_spec(t), rubrics=ctx.rubrics)
        except KeyError as e:
            raise SkillError(f"invalid table spec for {t.get('object_id')}: unknown {e}") from None
        if persist:
            persist_suite(ctx.store, s)
        doc = {"suite_id": s.suite_id, "object_id": s.spec.object_id, "tier": s.tier,
               "threshold_ref": s.threshold_ref, "normalisation_rule_version": s.normaliser.version,
               "levels": s.levels,
               "checks": [{"check_id": c.check_id, "level": c.level, "mode": c.mode, **c.definition} for c in s.checks]}
        docs.append(doc)
        suites.append({"suite_id": s.suite_id, "object_id": s.spec.object_id, "tier": s.tier,
                       "threshold_ref": s.threshold_ref, "active_levels": s.active_levels,
                       "checks": len(s.checks), "checks_by_level": dict(sorted(Counter(c.level for c in s.checks).items()))})
    path = out_dir(ctx, "generate_reconciliation_suite") / f"suites-{'-'.join(s['suite_id'] for s in suites)[:120]}.json"
    path.write_text(json.dumps(safe(docs), indent=2, sort_keys=True, default=str) + "\n")
    return safe({"suites": suites, "suite_path": str(path), "persisted": persist})


def _cluster_rows(ctx: Any, where: str, params: list) -> list[dict]:
    return ctx.store.query(
        "SELECT c.cluster_id, c.run_id, r.object_id, r.level, r.result, c.signature, c.known_issue_id, "
        "c.mismatch_count, c.confidence, c.rationale, r.mismatch_key_ref "
        f"FROM mismatch_cluster c JOIN validation_run r USING (run_id) WHERE {where} "
        "ORDER BY r.object_id, r.level, c.cluster_id", params)


def _review_state(ctx: Any, cluster_ids: list[str]) -> dict[str, str]:
    if not cluster_ids:
        return {}
    marks = ", ".join("?" for _ in cluster_ids)
    rows = ctx.store.query(f"SELECT subject_id, status FROM review_item WHERE subject_type = 'mismatch_cluster' "
                           f"AND subject_id IN ({marks})", cluster_ids)
    return {r["subject_id"]: r["status"] for r in rows}


def triage_mismatches(context: Any = None, run_id: str | None = None, suite_id: str | None = None,
                      object_id: str | None = None, source_path: str | None = None, target_path: str | None = None,
                      table: dict | None = None, run_label: str = "triage", as_of: str | None = None) -> dict:
    """Cluster reconciliation mismatches by root-cause signature and map them to Pattern Library known issues.

    Either reads clusters of an existing run (``run_id`` / ``suite_id`` / ``object_id``) from the store, or runs the
    table's suite in-boundary against two DuckDB databases (``source_path`` + ``target_path`` + ``table``) first.
    """
    ctx = coerce(context)
    executed = None
    if source_path or target_path or table:
        if not (source_path and target_path and table):
            raise SkillError("source_path, target_path and table are all required to run a reconciliation")
        import duckdb

        from altitude.validation import Endpoint, ValidationEngine, generate_suite

        for p in (source_path, target_path):
            if not Path(p).exists():
                raise SkillError(f"database {p!r} does not exist")
        spec = _spec(table)
        src, tgt = duckdb.connect(source_path, read_only=True), duckdb.connect(target_path, read_only=True)
        try:
            engine = ValidationEngine(ctx.store, Endpoint(src, "duckdb", "source"), Endpoint(tgt, "duckdb", "target"),
                                      out_dir(ctx, "triage_mismatches", "mismatch"), rubrics=ctx.rubrics)
            try:
                res = engine.run(generate_suite(spec, rubrics=ctx.rubrics), run_label=run_label,
                                 as_of=date.fromisoformat(as_of) if as_of else None)
            except ValueError as e:
                raise SkillError(str(e)) from None
        finally:
            src.close()
            tgt.close()
        executed = {"suite_id": res.suite.suite_id, "status": res.status,
                    "levels": {lv: {"result": r.result, "run_id": r.run_id, "mismatch_key_ref": r.mismatch_key_ref}
                               for lv, r in res.levels.items()}}
        run_ids = [r.run_id for r in res.levels.values()]
        rows = _cluster_rows(ctx, f"c.run_id IN ({', '.join('?' for _ in run_ids)})", run_ids)
    elif run_id:
        rows = _cluster_rows(ctx, "c.run_id = ?", [run_id])
    elif suite_id:
        rows = _cluster_rows(ctx, "r.suite_id = ?", [suite_id])
    elif object_id:
        rows = _cluster_rows(ctx, "r.object_id = ?", [object_id])
    else:
        raise SkillError("give run_id, suite_id or object_id, or source_path + target_path + table")
    review = _review_state(ctx, [r["cluster_id"] for r in rows])
    clusters = [{**r, "review_status": review.get(r["cluster_id"]),
                 "root_cause": not str(r["rationale"]).startswith("Explained by")} for r in rows]
    primary = [c for c in clusters if c["root_cause"]]
    return safe({
        "run": executed, "clusters": clusters, "cluster_count": len(clusters), "root_cause_clusters": len(primary),
        "mismatched_rows": sum(int(c["mismatch_count"] or 0) for c in primary),
        "known_issues": sorted({c["known_issue_id"] for c in clusters if c["known_issue_id"]}),
        "unmapped": sum(1 for c in clusters if not c["known_issue_id"]),
    })
