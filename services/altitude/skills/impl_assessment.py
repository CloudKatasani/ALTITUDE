"""Skill adapters for source harvest (``altitude_connectors``) and the assessment engine (``altitude.assessment``)."""

from __future__ import annotations

import fnmatch
import importlib.util
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from .context import coerce
from .impl_common import open_snapshot, out_dir, safe
from .registry import SkillError

SAMPLE_SYSTEMS = {"sqlserver": "SalesDW", "oracle": "ORAPROD", "teradata": "TDPROD"}
SAMPLE_SCRIPT_DIRS = {"sqlserver": ["ssis"], "teradata": ["bteq"]}


def _sample_estate(source: str):
    """The bundled emulated estate for ``source`` (``tests/fixtures/<source>/estate.py``)."""
    from altitude.core.paths import repo_root

    path = repo_root() / "tests" / "fixtures" / source / "estate.py"
    if not path.exists():
        raise SkillError(f"no bundled sample estate for {source!r} ({path} not found)")
    spec = importlib.util.spec_from_file_location(f"altitude_sample_estate_{source}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def harvest_source(context: Any = None, source: str = "", engagement_id: str = "ENG-LOCAL",
                   system_name: str | None = None, duckdb_path: str | None = None, attach: dict | None = None,
                   script_dirs: list | None = None, as_of: str | None = None) -> dict:
    """Harvest a source estate read-only (bundled sample, or an exported catalog in DuckDB) and seal a snapshot."""
    import duckdb

    from altitude.core.ids import stable_id
    from altitude.core.snapshot import Snapshot
    from altitude_connectors import ExtractionAgent

    ctx = coerce(context)
    scripts = [Path(p) for p in script_dirs or []]
    if duckdb_path:
        if not Path(duckdb_path).exists():
            raise SkillError(f"duckdb_path {duckdb_path!r} does not exist")
        con = duckdb.connect(duckdb_path, read_only=True)
        for name, path in sorted((attach or {}).items()):
            if not name.isidentifier():
                raise SkillError(f"invalid catalog name {name!r}")
            quoted = str(path).replace("'", "''")
            con.execute(f"ATTACH '{quoted}' AS {name} (READ_ONLY)")
        system = system_name or Path(duckdb_path).stem
        when = datetime.fromisoformat(as_of) if as_of else None
        sample = False
    else:
        est = _sample_estate(source)
        con = est.build()
        system = system_name or SAMPLE_SYSTEMS[source]
        scripts = scripts or [est.HERE / d for d in SAMPLE_SCRIPT_DIRS.get(source, [])]
        when = datetime.fromisoformat(as_of) if as_of else est.AS_OF
        sample = True
    agent = ExtractionAgent(source, con, engagement_id=engagement_id, system_name=system, script_dirs=scripts,
                            execute_dialect="duckdb", as_of=when)
    try:
        bundle = agent.harvest()
    finally:
        con.close()  # shipping uses the harvested bundle only
    directory = out_dir(ctx, "harvest_source", source)
    sid = stable_id("HRV", bundle.source_system["source_system_id"], bundle.content_hash())
    existing = directory / f"{sid}.duckdb"
    if existing.exists():  # snapshots are immutable: reuse the sealed one, refresh the canonical rows
        agent.ship(store=ctx.store)
        snap = Snapshot.open(existing, verify=True)
        snap.register(ctx.store)
    else:
        snap = agent.ship(snapshot_dir=directory, store=ctx.store)
    return {"snapshot_id": snap.snapshot_id, "path": str(snap.path), "content_hash": snap.content_hash,
            "source": source, "sample_estate": sample, "system_name": system,
            "source_system_id": bundle.source_system["source_system_id"], "engagement_id": engagement_id,
            "counts": bundle.counts(), "statements": bundle.meta["statements"], "refused": bundle.meta["refused"]}


def _registered_assessment(ctx: Any, harvest_snapshot_id: str):
    """An assessment of this harvest under the current rubric version already sealed and registered, if any."""
    import json

    from altitude.assessment import load_assessment

    for row in ctx.store.query("SELECT location, manifest FROM snapshot WHERE kind = 'assessment' ORDER BY snapshot_id"):
        manifest = row["manifest"] if isinstance(row["manifest"], dict) else json.loads(row["manifest"])
        meta = manifest.get("metadata", {})
        if (meta.get("harvest_snapshot_id") == harvest_snapshot_id and meta.get("rubric_version") == ctx.rubrics.version
                and Path(row["location"]).exists()):
            return load_assessment(row["location"])
    return None


def _assessment(ctx: Any, harvest_ref: str, tenant_id: str | None = None):
    import json

    from altitude.assessment import load_assessment, record, run_assessment
    from altitude.core.errors import AppendOnlyViolation

    harvest = open_snapshot(ctx, harvest_ref)
    if harvest.manifest.get("kind") != "harvest":
        raise SkillError(f"snapshot {harvest.snapshot_id} is a {harvest.manifest.get('kind')!r} snapshot, not a harvest")
    existing = _registered_assessment(ctx, harvest.snapshot_id)
    if existing is not None:  # snapshots are immutable: same harvest + rubric version => reuse the sealed result
        return existing
    directory = out_dir(ctx, "run_assessment")
    try:
        return run_assessment(harvest, directory, rubrics=ctx.rubrics, store=ctx.store, tenant_id=tenant_id)
    except AppendOnlyViolation:  # sealed in this workspace by another store: reuse it and record it here
        for manifest_path in sorted(directory.glob("*.manifest.json")):
            meta = json.loads(manifest_path.read_text()).get("metadata", {})
            if (meta.get("harvest_snapshot_id") == harvest.snapshot_id
                    and meta.get("rubric_version") == ctx.rubrics.version):
                result = load_assessment(manifest_path.with_name(manifest_path.name.replace(".manifest.json",
                                                                                            ".duckdb")))
                record(result, ctx.store, ctx.rubrics, tenant_id)
                return result
        raise


def run_assessment(context: Any = None, harvest_snapshot_id: str = "", report: bool = True,
                   tenant_id: str | None = None) -> dict:
    """Assess a sealed harvest snapshot: dispositions, complexity, anti-patterns, drift risk; export the report."""
    from altitude.assessment.report import export_report

    ctx = coerce(context)
    result = _assessment(ctx, harvest_snapshot_id, tenant_id)
    s = result.summary
    out = {"snapshot_id": result.snapshot_id, "path": str(result.snapshot.path),
           "harvest_snapshot_id": result.harvest_snapshot_id, "rubric_version": result.rubric_version,
           "source": s.get("source"), "objects": s.get("objects"), "objects_by_type": s.get("objects_by_type"),
           "dispositions": s.get("dispositions"), "complexity_bands": s.get("complexity_bands"),
           "review_items": s.get("review_items"), "objects_classified_pct": s.get("objects_classified_pct"),
           "anti_pattern_hits": s.get("anti_pattern_hits"), "anti_patterns_by_id": s.get("anti_patterns_by_id"),
           "anti_pattern_usd_month": s.get("anti_pattern_usd_month"),
           "drift_scan": (s.get("drift_scan") or {}).get("status"), "drift_hits_by_issue": s.get("drift_hits_by_issue")}
    if report:
        written = export_report(result, out_dir(ctx, "run_assessment", "reports", result.snapshot_id))
        out["report"] = {k: str(v) for k, v in sorted(written.items())}
    return safe(out)


def classify_objects(context: Any = None, harvest_snapshot_id: str = "", names: list | None = None,
                     object_types: list | None = None, dispositions: list | None = None,
                     needs_review_only: bool = False, top: int = 50) -> dict:
    """Disposition (keep/retire/rewrite...) per object with confidence, rule and rationale; filterable."""
    ctx = coerce(context)
    result = _assessment(ctx, harvest_snapshot_id)
    inv = result.rows("object_assessment")

    def keep(r: dict) -> bool:
        if names and not any(fnmatch.fnmatch(r["fq_name"].lower(), n.lower()) for n in names):
            return False
        if object_types and r["object_type"] not in object_types:
            return False
        if dispositions and r["disposition"] not in dispositions:
            return False
        return not needs_review_only or bool(r["needs_review"])

    rows = [r for r in inv if keep(r)]
    return safe({
        "assessment_snapshot_id": result.snapshot_id, "harvest_snapshot_id": result.harvest_snapshot_id,
        "rubric_version": result.rubric_version, "matched": len(rows),
        "dispositions": dict(sorted(Counter(r["disposition"] for r in rows).items())),
        "needs_review": sum(1 for r in rows if r["needs_review"]),
        "objects": [{k: r[k] for k in ("object_id", "fq_name", "object_type", "disposition", "confidence", "rule",
                                        "needs_review", "rationale", "complexity_band", "usage_90d")}
                    for r in rows[:top]],
        "truncated": len(rows) > len(rows[:top]),
    })
