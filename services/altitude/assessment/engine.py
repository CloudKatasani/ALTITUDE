"""Assessment engine (M3): harvest snapshot + rubric → sealed assessment snapshot.

Pure function of (harvest snapshot, rubric version, drift scanner, AI provider):
outputs carry no wall-clock or random values, rows are sorted, numbers are
rounded, and the assessment snapshot id is derived from its inputs and
content — so re-running on the same snapshot and rubric reproduces identical
scores and an identical snapshot hash. Side effects (store rows, review queue)
are optional and idempotent.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from altitude.core.ai import Inference, Provider, ReviewQueue
from altitude.core.ids import canonical_json, content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.snapshot import Snapshot, SnapshotWriter

from . import anti_patterns as ap
from . import drift as drift_mod
from .complexity import score_object
from .disposition import PROMPT_TEMPLATE, DispositionClassifier
from .estate import Estate

ENGINE = "altitude.assessment@1.0.0"

TABLES: dict[str, dict[str, str]] = {
    "object_assessment": {
        "object_id": "VARCHAR", "fq_name": "VARCHAR", "object_type": "VARCHAR", "loc": "INTEGER",
        "usage_90d": "INTEGER", "last_used_at": "TIMESTAMP", "disposition": "VARCHAR", "confidence": "DECIMAL(4,3)",
        "rule": "VARCHAR", "needs_review": "BOOLEAN", "rationale": "VARCHAR", "complexity_score": "DECIMAL(6,2)",
        "complexity_band": "VARCHAR", "anti_pattern_hits": "INTEGER", "credits_month": "DECIMAL(14,4)",
        "drift_hits": "INTEGER",
    },
    "object_disposition": {
        "object_id": "VARCHAR", "disposition": "VARCHAR", "confidence": "DECIMAL(4,3)", "rationale": "VARCHAR",
        "rule": "VARCHAR", "signals": "VARCHAR", "needs_review": "BOOLEAN", "provider": "VARCHAR",
        "model_id": "VARCHAR", "prompt_template": "VARCHAR",
    },
    "complexity_score": {"object_id": "VARCHAR", "score": "DECIMAL(6,2)", "band": "VARCHAR", "factors": "VARCHAR"},
    "anti_pattern_hit": {
        "hit_id": "VARCHAR", "object_id": "VARCHAR", "fq_name": "VARCHAR", "pattern_id": "VARCHAR",
        "pattern": "VARCHAR", "severity": "VARCHAR", "line": "INTEGER", "snippet": "VARCHAR", "evidence": "VARCHAR",
        "target_object_id": "VARCHAR", "credits_month": "DECIMAL(14,4)", "usd_month": "DECIMAL(14,2)",
        "impact": "VARCHAR", "recommendation": "VARCHAR",
    },
    "drift_hit": {
        "hit_id": "VARCHAR", "object_id": "VARCHAR", "fq_name": "VARCHAR", "issue_id": "VARCHAR",
        "severity": "VARCHAR", "line": "INTEGER", "snippet": "VARCHAR", "message": "VARCHAR",
        "confidence": "DECIMAL(4,3)", "rationale": "VARCHAR",
    },
    "assessment_summary": {"key": "VARCHAR", "value": "VARCHAR"},
}


@dataclass
class AssessmentResult:
    snapshot: Snapshot
    harvest_snapshot_id: str
    rubric_version: str
    tables: dict[str, list[dict[str, Any]]]
    summary: dict[str, Any]

    @property
    def snapshot_id(self) -> str:
        return self.snapshot.snapshot_id

    def rows(self, table: str) -> list[dict[str, Any]]:
        return self.tables[table]

    def review_items(self) -> list[dict[str, Any]]:
        return [r for r in self.tables["object_disposition"] if r["needs_review"]]


def _jsonable(rows: list[dict[str, Any]], cols: dict[str, str]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        row = {}
        for c in cols:
            v = r.get(c)
            row[c] = canonical_json(v) if isinstance(v, (dict, list)) else v
        out.append(row)
    return out


def assess(harvest: Snapshot, rubrics: RubricSet | None = None, provider: Provider | None = None) -> tuple[
        dict[str, list[dict[str, Any]]], dict[str, Any], dict[str, Any]]:
    """Compute all assessment tables (no side effects). Returns (tables, summary, metadata)."""
    rubrics = rubrics or default_rubrics()
    estate = Estate(harvest)
    drift = drift_mod.scan(estate)
    drift_counts = drift.counts_by_object()
    complexity = {oid: score_object(o, estate, rubrics, drift_counts.get(oid)) for oid, o in estate.objects.items()}
    hits = ap.detect(estate, rubrics)
    dispositions = DispositionClassifier(rubrics, provider).classify(estate, complexity)

    hits_by_obj = Counter(h["object_id"] for h in hits)
    credits_by_obj: dict[str, float] = {}
    for h in hits:
        credits_by_obj[h["object_id"]] = round(credits_by_obj.get(h["object_id"], 0.0) + h["credits_month"], 4)
    drift_by_obj = Counter(h["object_id"] for h in drift.hits)

    disp_rows, inv_rows = [], []
    for d in dispositions:
        o = estate.objects[d.object_id]
        cx = complexity[d.object_id]
        disp_rows.append({"object_id": d.object_id, "disposition": d.disposition, "confidence": d.confidence,
                          "rationale": d.rationale, "rule": d.rule, "signals": d.signals,
                          "needs_review": d.needs_review, "provider": d.provider, "model_id": d.model_id,
                          "prompt_template": PROMPT_TEMPLATE})
        inv_rows.append({"object_id": d.object_id, "fq_name": o.fq_name, "object_type": o.object_type, "loc": o.loc,
                         "usage_90d": o.usage_90d, "last_used_at": o.last_used_at, "disposition": d.disposition,
                         "confidence": d.confidence, "rule": d.rule, "needs_review": d.needs_review,
                         "rationale": d.rationale, "complexity_score": cx.score, "complexity_band": cx.band,
                         "anti_pattern_hits": hits_by_obj.get(d.object_id, 0),
                         "credits_month": credits_by_obj.get(d.object_id, 0.0),
                         "drift_hits": drift_by_obj.get(d.object_id, 0)})
    cx_rows = [{"object_id": oid, "score": c.score, "band": c.band, "factors": c.factors}
               for oid, c in sorted(complexity.items())]

    total = len(dispositions)
    review = sum(1 for d in dispositions if d.needs_review)
    summary = {
        "engine": ENGINE,
        "harvest_snapshot_id": harvest.snapshot_id,
        "harvest_content_hash": harvest.content_hash,
        "rubric_version": rubrics.version,
        "as_of": estate.as_of.isoformat() if estate.as_of else None,
        "source": estate.dialect,
        "engagement_id": estate.engagement_id,
        "objects": total,
        "objects_by_type": dict(sorted(Counter(o.object_type for o in estate.objects.values()).items())),
        "dispositions": dict(sorted(Counter(d.disposition for d in dispositions).items())),
        "complexity_bands": dict(sorted(Counter(c.band for c in complexity.values()).items())),
        "review_items": review,
        "objects_classified_pct": round(100.0 * (total - review) / total, 2) if total else 0.0,
        "anti_pattern_hits": len(hits),
        "anti_patterns_by_id": dict(sorted(Counter(h["pattern_id"] for h in hits).items())),
        "anti_pattern_credits_month": round(sum(h["credits_month"] for h in hits), 4),
        "anti_pattern_usd_month": round(sum(h["usd_month"] for h in hits), 2),
        "drift_scan": drift.summary(),
        "drift_hits_by_issue": dict(sorted(Counter(h["issue_id"] for h in drift.hits).items())),
        "usage_history_days": estate.history_days,
        "provider": dispositions[0].provider if dispositions else "template",
    }
    tables = {
        "object_assessment": inv_rows,
        "object_disposition": disp_rows,
        "complexity_score": cx_rows,
        "anti_pattern_hit": hits,
        "drift_hit": drift.hits,
        "assessment_summary": [{"key": k, "value": canonical_json(v)} for k, v in sorted(summary.items())],
    }
    meta = {"engagement_id": estate.engagement_id, "harvest_snapshot_id": harvest.snapshot_id,
            "rubric_version": rubrics.version, "drift_scan": drift.status, "as_of": summary["as_of"],
            "source": estate.dialect, "engine": ENGINE}
    return tables, summary, meta


def run_assessment(harvest: Snapshot | str | Path, out_dir: str | Path, *, rubrics: RubricSet | None = None,
                   store: Any = None, provider: Provider | None = None, snapshot_id: str | None = None,
                   tenant_id: str | None = None) -> AssessmentResult:
    """Assess a sealed harvest snapshot and seal the results as an assessment snapshot."""
    if not isinstance(harvest, Snapshot):
        harvest = Snapshot.open(harvest, verify=True)
    else:
        harvest.verify()
    rubrics = rubrics or default_rubrics()
    tables, summary, meta = assess(harvest, rubrics, provider)
    prepared = {name: _jsonable(rows, TABLES[name]) for name, rows in tables.items()}
    snapshot_id = snapshot_id or stable_id("ASM", harvest.snapshot_id, rubrics.version, content_hash(prepared, 32))
    w = SnapshotWriter(out_dir, snapshot_id, kind="assessment", metadata=meta)
    for name, rows in prepared.items():
        w.add_table_from_rows(name, rows, TABLES[name])
    sealed_at = datetime.fromisoformat(summary["as_of"]) if summary["as_of"] else None
    snap = w.seal(sealed_at=sealed_at)
    result = AssessmentResult(snap, harvest.snapshot_id, rubrics.version, tables, summary)
    if store is not None:
        record(result, store, rubrics, tenant_id)
    return result


def record(result: AssessmentResult, store: Any, rubrics: RubricSet | None = None, tenant_id: str | None = None) -> None:
    """Persist an assessment into the control plane (idempotent) and route low-confidence items to review."""
    rubrics = rubrics or default_rubrics()
    sid = result.snapshot_id
    result.snapshot.register(store)
    if store.get("assessment_run", assessment_id=sid):
        return
    queue = ReviewQueue(store, rubrics)
    inputs_ref = f"snapshot:{result.harvest_snapshot_id}"
    known = {r["object_id"] for r in store.query("SELECT object_id FROM source_object")}
    cx = {r["object_id"]: r for r in result.tables["complexity_score"]}
    for d in result.tables["object_disposition"]:
        inf = Inference(kind="disposition", subject_type="object_disposition", subject_id=d["object_id"],
                        output=d["disposition"], confidence=float(d["confidence"]), rationale=d["rationale"],
                        model_id=d["model_id"], prompt_template=d["prompt_template"], provider=d["provider"],
                        inputs_ref=inputs_ref, tenant_id=tenant_id)
        queue.record(inf)
        store.insert("object_disposition", {"object_id": d["object_id"], "snapshot_id": sid,
                                            "disposition": d["disposition"], "confidence": d["confidence"],
                                            "rationale": d["rationale"], "proposed_by": ENGINE if d["provider"] == "template"
                                            else f"{d['provider']}:{d['model_id']}", "confirmed_by": None})
        c = cx[d["object_id"]]
        store.insert("complexity_score", {"object_id": d["object_id"], "snapshot_id": sid, "score": c["score"],
                                          "band": c["band"], "factors": c["factors"],
                                          "rubric_version": result.rubric_version})
        if d["object_id"] in known:
            values: dict[str, Any] = {"complexity_score": c["score"]}
            if not d["needs_review"]:  # low-confidence proposals have no effect until a human approves
                values.update({"disposition": d["disposition"], "disposition_conf": d["confidence"],
                               "disposition_rationale": d["rationale"][:1000]})
            store.update("source_object", {"object_id": d["object_id"]}, values)
    for h in result.tables["anti_pattern_hit"]:
        store.insert("anti_pattern_hit", {"hit_id": h["hit_id"], "snapshot_id": sid, "object_id": h["object_id"],
                                          "pattern_id": h["pattern_id"], "severity": h["severity"], "line": h["line"],
                                          "snippet": h["snippet"], "credits_month": h["credits_month"],
                                          "impact": h["impact"]})
    for h in result.tables["drift_hit"]:
        store.insert("drift_hit", {"hit_id": h["hit_id"], "snapshot_id": sid, **{k: h[k] for k in (
            "object_id", "issue_id", "severity", "line", "snippet", "message", "confidence", "rationale")}})
    s = result.summary
    store.insert("assessment_run", {"assessment_id": sid, "engagement_id": s["engagement_id"],
                                    "harvest_snapshot_id": result.harvest_snapshot_id,
                                    "rubric_version": result.rubric_version,
                                    "drift_scan_status": s["drift_scan"]["status"], "objects": s["objects"],
                                    "review_items": s["review_items"], "summary": s})


def load_assessment(path: str | Path | Snapshot) -> AssessmentResult:
    """Re-open a sealed assessment snapshot (for reports, planning and gates)."""
    snap = path if isinstance(path, Snapshot) else Snapshot.open(path, verify=True)
    tables: dict[str, list[dict[str, Any]]] = {}
    for name, cols in TABLES.items():
        order = "object_id" if "object_id" in cols else ("key" if name == "assessment_summary" else "1")
        rows = snap.query(f'SELECT * FROM "{name}" ORDER BY {order}' + (", hit_id" if "hit_id" in cols else ""))
        for r in rows:
            for c, v in list(r.items()):
                if c in {"signals", "factors", "evidence", "impact"} and isinstance(v, str):
                    r[c] = json.loads(v)
                elif hasattr(v, "as_tuple"):  # Decimal → float for computation
                    r[c] = float(v)
        tables[name] = rows
    summary = {r["key"]: json.loads(r["value"]) for r in tables["assessment_summary"]}
    return AssessmentResult(snap, summary["harvest_snapshot_id"], summary["rubric_version"], tables, summary)
