"""Suggestion engine (Section 6.5).

    Harvest (sealed snapshot)
      → Signals (SQL detectors per check, run against the snapshot)
        → Rule evaluation (rubric thresholds bound as $parameters)
          → Root-cause clustering (query signature · warehouse · dashboard · pipeline · owner)
            → Value model ($ p50 / conservative, annualised, with method; risk = likelihood × impact)
              → Remediation generator (SQL / dbt drafts, header-stamped, each with a rollback)
                → AI narrative (altitude.core.ai provider; confidence from evidence completeness)
                  → Review flags (mandatory below rubric.ai.review_confidence_min; sampled above)
                    → Prioritisation (value × effort × risk → quadrant + rank) → publish

Determinism: the engine reads only the sealed snapshot, the rubric and the catalogue; it uses no
wall-clock or random values, runs DuckDB single-threaded and rounds metrics, so the same snapshot +
rubric version reproduce identical scores, values and exported bytes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import jinja2

from altitude.core.ai import Inference, Provider, TemplateProvider, fence_untrusted, requires_review, sampled_for_review
from altitude.core.generated import stamp
from altitude.core.ids import canonical_json, content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.snapshot import Snapshot

from . import formula
from .catalogue import UNIT_REFS, Catalogue, Check, default_catalogue

PROMPT_TEMPLATE = "diagnostics.suggestion_narrative@1.0.0"
NARRATIVE_SYSTEM = (
    "You are a senior Snowflake platform consultant. Write a concise, factual explanation of one diagnostic "
    "suggestion for an executive and a platform engineer. Use only the facts provided; do not invent numbers."
)
QUADRANT_ORDER = ["quick_win", "strategic", "hygiene", "defer"]
REMEDIATION_EXT = {"sql": ".sql", "dbt": ".sql", "terraform": ".tf"}
METRIC_DIGITS = 6


# --------------------------------------------------------------------------- data classes


@dataclass
class SnapshotContext:
    snapshot_id: str
    path: Path
    manifest: dict
    window_start: datetime
    window_end: datetime
    window_days: float
    as_of: datetime
    inputs: dict[str, Any]
    price_per_credit: float
    storage_price_per_tb_month: float
    price_source: str
    storage_price_source: str
    harvest_status: dict[str, str]
    account: dict[str, Any]

    @property
    def sealed_at(self) -> str:
        return self.manifest.get("sealed_at", "")

    def table_available(self, table: str) -> bool:
        return table in self.manifest.get("tables", {}) and self.harvest_status.get(table, "ok") != "unavailable"

    @property
    def annualise(self) -> float:
        return 0.0 if not self.window_days else self._days_per_year / self.window_days

    _days_per_year: float = 0.0


@dataclass
class CheckOutcome:
    check_id: str
    status: str                 # pass | fail | not_evaluated
    candidates: int
    flagged: int
    missing: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SuggestionDetail:
    record: dict                # canonical record (Section 6.5)
    severity: str
    cluster_dimension: str
    cluster_key: str
    narrative: str
    confidence_rationale: str
    needs_review: bool
    review_reason: str | None
    priority_score: float
    value_rows: list[dict]
    artifacts: dict[str, str]   # relative path -> content (stamped)
    inference: Inference

    @property
    def id(self) -> str:
        return self.record["id"]


@dataclass
class DiagnosticResult:
    snapshot_id: str
    rubric_version: str
    catalogue_hash: str
    tier: str
    context: SnapshotContext
    outcomes: list[CheckOutcome]
    details: list[SuggestionDetail]             # published (tier scope / top-N applied)
    all_details: list[SuggestionDetail]         # every suggestion produced in scope
    evidence: list[dict]
    scorecard: dict
    recommendations: list[dict]
    assumptions: list[dict]

    @property
    def suggestions(self) -> list[dict]:
        return [d.record for d in self.details]

    def detail(self, suggestion_id: str) -> SuggestionDetail:
        for d in self.all_details:
            if d.id == suggestion_id:
                return d
        raise KeyError(suggestion_id)

    @property
    def stamp(self) -> dict:
        return {"snapshot_id": self.snapshot_id, "rubric_version": self.rubric_version,
                "catalogue_hash": self.catalogue_hash, "tier": self.tier}

    def findings(self) -> list[dict]:
        """``score_detection``-compatible findings: one per published suggestion."""
        return [{"check_id": s["check_id"], "affected_objects": list(s["affected_objects"])} for s in self.suggestions]

    def evidence_for(self, suggestion: dict) -> list[dict]:
        refs = set(suggestion["evidence_refs"])
        return [e for e in self.evidence if e["id"] in refs]


# --------------------------------------------------------------------------- helpers


def _plain(v: Any) -> Any:
    """DuckDB value -> stable Python value (floats rounded so reruns are byte-identical)."""
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        r = round(v, METRIC_DIGITS)
        return 0.0 if r == 0 else r
    return v


def json_safe(v: Any) -> Any:
    if isinstance(v, (datetime, date, time)):
        return v.isoformat()
    if isinstance(v, dict):
        return {k: json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [json_safe(x) for x in v]
    return _plain(v)


def _decode_inputs(con: duckdb.DuckDBPyConnection) -> dict[str, Any]:
    try:
        rows = con.execute('SELECT "KEY", CAST("VALUE" AS VARCHAR) FROM CLIENT_INPUTS ORDER BY 1').fetchall()
    except duckdb.Error:
        return {}
    out = {}
    for k, v in rows:
        try:
            out[k] = json.loads(v) if v is not None else None
        except (TypeError, ValueError):
            out[k] = v
    return out


def _window(con: duckdb.DuckDBPyConnection, metadata: dict) -> tuple[datetime, datetime]:
    if metadata.get("window_start") and metadata.get("window_end"):
        start = datetime.fromisoformat(str(metadata["window_start"]))
        end = datetime.fromisoformat(str(metadata["window_end"]))
    else:
        row = con.execute("SELECT min(START_TIME), max(START_TIME) FROM WAREHOUSE_METERING_HISTORY").fetchone()
        if not row or row[0] is None:
            row = con.execute("SELECT min(START_TIME), max(START_TIME) FROM QUERY_HISTORY").fetchone()
        start, end = row
    start = datetime(start.year, start.month, start.day)
    end = datetime(end.year, end.month, end.day)
    return start, end


def open_context(snapshot: Snapshot, con: duckdb.DuckDBPyConnection, rubrics: RubricSet) -> SnapshotContext:
    manifest = snapshot.manifest
    meta = manifest.get("metadata", {})
    start, end = _window(con, meta)
    window_days = float((end - start).days + 1)
    inputs = _decode_inputs(con)
    price = inputs.get("contract_price_per_credit")
    storage = inputs.get("storage_price_per_tb_month")
    try:
        account_rows = con.execute("SELECT * FROM ACCOUNT_INFO LIMIT 1")
        cols = [d[0] for d in account_rows.description]
        first = account_rows.fetchone()
        account = dict(zip(cols, first)) if first else {}
    except duckdb.Error:
        account = {}
    ctx = SnapshotContext(
        snapshot_id=snapshot.snapshot_id,
        path=Path(snapshot.path),
        manifest=manifest,
        window_start=start,
        window_end=end,
        window_days=window_days,
        as_of=end + timedelta(days=1),
        inputs=inputs,
        price_per_credit=float(price) if price is not None else float(rubrics.get("rubric.diagnostics.pricing.default_price_per_credit")),
        storage_price_per_tb_month=float(storage) if storage is not None
        else float(rubrics.get("rubric.diagnostics.pricing.default_storage_price_per_tb_month")),
        price_source="client_input" if price is not None else "rubric_default",
        storage_price_source="client_input" if storage is not None else "rubric_default",
        harvest_status=dict(meta.get("harvest_status", {})),
        account=account,
    )
    ctx._days_per_year = float(rubrics.get(UNIT_REFS["days_per_year"]))
    return ctx


def create_helpers(con: duckdb.DuckDBPyConnection, catalogue: Catalogue, rubrics: RubricSet) -> None:
    """Shared helper relations as TEMP objects (the sealed snapshot is never modified)."""
    for h in catalogue.helpers:
        if h["kind"] == "rubric_map":
            mapping = rubrics.get(h["ref"])
            con.execute(f'CREATE OR REPLACE TEMP TABLE {h["name"]} ("{h["key_column"]}" VARCHAR, "{h["value_column"]}" DOUBLE)')
            con.executemany(f"INSERT INTO {h['name']} VALUES (?, ?)", [[k, float(v)] for k, v in sorted(mapping.items())])
        else:
            con.execute(f"CREATE OR REPLACE TEMP VIEW {h['name']} AS {h['sql']}")


def standard_params(ctx: SnapshotContext, rubrics: RubricSet) -> dict[str, Any]:
    out: dict[str, Any] = {
        "window_start": ctx.window_start,
        "window_end": ctx.window_end,
        "window_days": ctx.window_days,
        "as_of": ctx.as_of,
        "price_per_credit": ctx.price_per_credit,
        "storage_price_per_tb_month": ctx.storage_price_per_tb_month,
    }
    for name, ref in UNIT_REFS.items():
        out[name] = rubrics.get(ref)
    return out


def catalogue_hash(catalogue: Catalogue) -> str:
    return content_hash({
        "checks": [c.raw for c in catalogue.checks],
        "helpers": catalogue.helpers,
        "domains": catalogue.domains,
        "tiers": catalogue.tiers,
        "recommendations": catalogue.recommendations,
    }, 12)


def _tidy(text: str) -> str:
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    for ln in lines:
        if not ln and out and not out[-1]:
            continue
        out.append(ln)
    while out and not out[-1]:
        out.pop()
    while out and not out[0]:
        out.pop(0)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------- engine


class DiagnosticsEngine:
    def __init__(self, rubrics: RubricSet | None = None, catalogue: Catalogue | None = None,
                 provider: Provider | None = None):
        self.rubrics = rubrics or default_rubrics()
        self.catalogue = catalogue or default_catalogue()
        self.provider = provider
        self.env = jinja2.Environment(undefined=jinja2.StrictUndefined, autoescape=False, keep_trailing_newline=True)
        self.env.globals.update(usd=self.usd, pct=self.pct, num=self.num, gb=self.gb, tb=self.tb)

    # ---------------------------------------------------------------- formatting (templates)
    @staticmethod
    def usd(x: Any) -> str:
        return f"${float(x or 0):,.0f}" if abs(float(x or 0)) >= 1 else f"${float(x or 0):,.2f}"

    @staticmethod
    def pct(x: Any) -> str:
        v = float(x or 0) * 100
        return f"{v:.0f}%" if abs(v) >= 1 or v == 0 else f"{v:.1f}%"

    @staticmethod
    def num(x: Any) -> str:
        v = float(x or 0)
        return f"{v:,.0f}" if abs(v) >= 1 or v == 0 else f"{v:.2f}"

    def gb(self, x: Any) -> str:
        return f"{float(x or 0) / float(self.rubrics.get(UNIT_REFS['bytes_per_gb'])):,.1f} GB"

    def tb(self, x: Any) -> str:
        return f"{float(x or 0) / float(self.rubrics.get(UNIT_REFS['bytes_per_tb'])):,.2f} TB"

    def render(self, template: str, ctx: dict) -> str:
        return self.env.from_string(template).render(**ctx)

    # ---------------------------------------------------------------- detectors
    def run_detector(self, con: duckdb.DuckDBPyConnection, check: Check, std: dict[str, Any]) -> tuple[list[dict], dict]:
        params = {**std, **check.resolve_params(self.rubrics)}
        bound = {k: params[k] for k in check.referenced_params()}
        missing = [k for k in check.referenced_params() if k not in params]
        if missing:
            raise KeyError(f"{check.id}: unbound detector parameters {missing}")
        try:
            cur = con.execute(check.detector_sql(), bound)
        except duckdb.Error as e:
            raise RuntimeError(f"{check.id}: detector failed: {e}") from e
        cols = [d[0] for d in cur.description]
        rows = [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
        for r in rows:
            r["OBJECT_NAME"] = str(r["OBJECT_NAME"])
            r["CLUSTER_KEY"] = str(r["CLUSTER_KEY"]) if r.get("CLUSTER_KEY") is not None else "*"
            r["FLAGGED"] = bool(r["FLAGGED"])
        return rows, params

    # ---------------------------------------------------------------- main entry point
    def run(self, snapshot: Snapshot | str | Path, tier: str = "D2") -> DiagnosticResult:
        snap = snapshot if isinstance(snapshot, Snapshot) else Snapshot.open(snapshot)
        tier_def = self.catalogue.tier(tier)
        con = duckdb.connect(str(snap.path), read_only=True)
        try:
            con.execute("SET threads = 1")
            create_helpers(con, self.catalogue, self.rubrics)
            ctx = open_context(snap, con, self.rubrics)
            std = standard_params(ctx, self.rubrics)
            outcomes: list[CheckOutcome] = []
            details: list[SuggestionDetail] = []
            evidence: list[dict] = []
            for check in self.catalogue.checks_for_tier(tier):
                missing = [t for t in check.requires if not ctx.table_available(t)]
                if missing:
                    outcomes.append(CheckOutcome(check.id, "not_evaluated", 0, 0, missing=missing))
                    continue
                rows, params = self.run_detector(con, check, std)
                flagged = [r for r in rows if r["FLAGGED"]]
                outcomes.append(CheckOutcome(check.id, "fail" if flagged else "pass", len(rows), len(flagged)))
                clusters: dict[str, list[dict]] = {}
                for r in flagged:
                    clusters.setdefault(r["CLUSTER_KEY"], []).append(r)
                for key in sorted(clusters):
                    d, ev = self._build(check, key, clusters[key], len(rows), params, ctx)
                    details.append(d)
                    evidence.extend(ev)
        finally:
            con.close()

        self._prioritise(details)
        top = tier_def.get("top_findings")
        published = [d for d in details if not top or d.record["priority"]["rank"] <= int(top)]
        published.sort(key=lambda d: d.record["priority"]["rank"])
        pub_refs = {ref for d in published for ref in d.record["evidence_refs"]}
        from .scorecard import compute_scorecard, recommend

        scorecard = compute_scorecard(outcomes, self.catalogue, self.rubrics, tier)
        recs = recommend(details, scorecard, ctx.inputs, self.catalogue, self.rubrics)
        return DiagnosticResult(
            snapshot_id=ctx.snapshot_id,
            rubric_version=self.rubrics.version,
            catalogue_hash=catalogue_hash(self.catalogue),
            tier=tier,
            context=ctx,
            outcomes=outcomes,
            details=published,
            all_details=sorted(details, key=lambda d: d.record["priority"]["rank"]),
            evidence=sorted((e for e in evidence if e["id"] in pub_refs), key=lambda e: e["id"]),
            scorecard=scorecard,
            recommendations=recs,
            assumptions=self._assumptions(ctx),
        )

    # ---------------------------------------------------------------- per-cluster suggestion
    def _build(self, check: Check, cluster_key: str, rows: list[dict], candidates: int, params: dict,
               ctx: SnapshotContext) -> tuple[SuggestionDetail, list[dict]]:
        raw = check.raw
        rows = sorted(rows, key=lambda r: r["OBJECT_NAME"])
        sid = stable_id("SUG", ctx.snapshot_id, check.id, cluster_key)
        objects = sorted({r["OBJECT_NAME"] for r in rows})

        # evidence
        kind = raw["evidence"]["kind"]
        detector_sha = content_hash(check.detector_sql(), 12)
        bound = {k: json_safe(params[k]) for k in check.referenced_params()}
        ev_records = []
        for r in rows:
            ev_records.append({
                "id": stable_id(f"EV-{kind}", ctx.snapshot_id, check.id, cluster_key, r["OBJECT_NAME"]),
                "snapshot_id": ctx.snapshot_id,
                "check_id": check.id,
                "object": r["OBJECT_NAME"],
                "cluster_key": cluster_key,
                "kind": kind,
                "source_tables": check.requires,
                "metrics": {f: json_safe(r.get(f)) for f in raw["evidence"]["fields"]},
                "detector_ref": f"detectors/{check.id}.sql",
                "detector_sha": detector_sha,
                "params": bound,
            })
        evidence_refs = sorted(e["id"] for e in ev_records)

        # template context
        tctx = {
            "check": raw, "rows": rows, "objects": objects, "n": len(objects), "candidates": candidates,
            "params": params, "cluster_key": cluster_key, "snapshot_id": ctx.snapshot_id,
            "window_days": int(ctx.window_days), "price_per_credit": ctx.price_per_credit,
            "annualise": ctx.annualise, "inputs": ctx.inputs, "account": ctx.account,
        }

        # value model
        value = raw["value"]
        value_rows: list[dict] = []
        annualised = None
        if value.get("p50"):
            variables_base = {
                "price_per_credit": ctx.price_per_credit,
                "storage_price_per_tb_month": ctx.storage_price_per_tb_month,
                "annualise": ctx.annualise,
                "months_per_year": self.rubrics.get(UNIT_REFS["months_per_year"]),
                **{k: self.rubrics.get(ref) for k, ref in value.get("factors", {}).items()},
            }
            p50 = cons = 0.0
            for r in rows:
                variables = {**variables_base, **r}
                a = formula.evaluate(value["p50"], variables)
                b = formula.evaluate(value["conservative"], variables)
                p50 += a
                cons += b
                value_rows.append({"object": r["OBJECT_NAME"], "p50": round(a, 2), "conservative": round(b, 2)})
            annualised = {"p50": int(round(max(p50, 0.0))), "conservative": int(round(max(min(cons, p50), 0.0)))}

        risk_reduction = None
        if raw.get("risk"):
            lk = int(self.rubrics.get(raw["risk"]["likelihood_ref"]))
            im = int(self.rubrics.get(raw["risk"]["impact_ref"]))
            residual = int(self.rubrics.get("rubric.diagnostics.risk.residual_likelihood")) * im
            risk_reduction = {"likelihood": lk, "impact": im, "score": lk * im, "residual_score": residual,
                              "method": raw["risk"]["method"]}

        # effort
        size = raw["effort"]["size"]
        hours = float(self.rubrics.get(f"rubric.diagnostics.effort.hours_p50.{size}")) + \
            float(self.rubrics.get("rubric.diagnostics.effort.per_extra_object_hours")) * (len(objects) - 1)

        # confidence from evidence completeness
        confidence, conf_rationale = self._confidence(check, ctx)

        title = " ".join(self.render(raw["title_template"], tctx).split())
        rationale = " ".join(self.render(raw["rationale_template"], tctx).split()).rstrip(" ;,")
        if not rationale.endswith((".", "!", "?")):
            rationale += "."

        # remediation artifacts
        rem = raw["remediation"]
        ext = REMEDIATION_EXT[rem["type"]]
        artifact_ref = f"remediation/{sid}{ext}"
        rollback_ref = f"remediation/{sid}.rollback{ext}"
        source = f"{check.id} @ {ctx.snapshot_id}"
        head = self._artifact_header(sid, check, title, rem, ctx, rollback_ref, rollback=False)
        rhead = self._artifact_header(sid, check, title, rem, ctx, artifact_ref, rollback=True)
        artifacts = {
            artifact_ref: stamp(head + _tidy(self.render(rem["template"], tctx)), ext, source),
            rollback_ref: stamp(rhead + _tidy(self.render(rem["rollback"], tctx)), ext, source),
        }

        record = {
            "id": sid,
            "snapshot_id": ctx.snapshot_id,
            "check_id": check.id,
            "domain": check.domain,
            "waf_pillar": check.waf_pillar,
            "title": title,
            "evidence_refs": evidence_refs,
            "affected_objects": objects,
            "value": {"annualised_usd": annualised, "method": value["method"]},
            "risk_reduction": risk_reduction,
            "effort": {"size": size, "hours_p50": hours},
            "confidence": confidence,
            "rationale": rationale,
            "remediation": {"type": rem["type"], "artifact_ref": artifact_ref, "autonomy": rem["autonomy"],
                            "rollback_ref": rollback_ref},
            "kpis_to_watch": list(raw["kpis_to_watch"]),
            "priority": {"quadrant": "defer", "rank": 0},
            "status": "proposed",
            "reviewer": None,
        }

        narrative, inference = self._narrative(record, check, conf_rationale, ev_records)
        low = requires_review(confidence, self.rubrics)
        reason = "low_confidence" if low else ("sampled" if sampled_for_review(sid, self.rubrics) else None)
        detail = SuggestionDetail(
            record=record, severity=check.severity, cluster_dimension=check.cluster_by, cluster_key=cluster_key,
            narrative=narrative, confidence_rationale=conf_rationale, needs_review=low, review_reason=reason,
            priority_score=0.0, value_rows=value_rows, artifacts=artifacts, inference=inference,
        )
        return detail, ev_records

    def _artifact_header(self, sid: str, check: Check, title: str, rem: dict, ctx: SnapshotContext, other_ref: str,
                         rollback: bool) -> str:
        c = "--" if rem["type"] in ("sql", "dbt") else "#"
        kind = "ROLLBACK for" if rollback else "Remediation for"
        pair = "Forward script" if rollback else "Rollback"
        return (
            f"{c} {kind} {sid} ({check.id}): {title}\n"
            f"{c} Snapshot: {ctx.snapshot_id} | Rubric: {self.rubrics.version} | Autonomy: {rem['autonomy']} "
            f"(human approval required before execution)\n"
            f"{c} {pair}: {other_ref}\n"
        )

    def _confidence(self, check: Check, ctx: SnapshotContext) -> tuple[float, str]:
        base = float(self.rubrics.get(f"rubric.diagnostics.confidence.base.{check.raw['confidence_class']}"))
        floor = float(self.rubrics.get("rubric.diagnostics.confidence.completeness_floor"))
        w_input = float(self.rubrics.get("rubric.diagnostics.confidence.missing_input_penalty"))
        target = float(self.rubrics.get("rubric.diagnostics.window.target_days"))
        tables_ok = [t for t in check.requires if ctx.table_available(t)]
        inputs_ok = [k for k in check.inputs if ctx.inputs.get(k) is not None]
        coverage = min(1.0, ctx.window_days / target) if target else 1.0
        denom = len(check.requires) + w_input * len(check.inputs) + 1.0
        completeness = (len(tables_ok) + w_input * len(inputs_ok) + coverage) / denom
        conf = round(base * (floor + (1.0 - floor) * completeness), 3)
        missing_inputs = sorted(set(check.inputs) - set(inputs_ok))
        text = (
            f"Detector class '{check.raw['confidence_class']}' (base {base:.2f}); evidence completeness "
            f"{completeness:.0%}: {len(tables_ok)}/{len(check.requires)} source tables, "
            f"{len(inputs_ok)}/{len(check.inputs)} client inputs, window {int(ctx.window_days)}/{int(target)} days"
            + (f"; missing inputs: {', '.join(missing_inputs)}" if missing_inputs else "")
        )
        return conf, text

    def _narrative(self, record: dict, check: Check, conf_rationale: str, ev: list[dict]) -> tuple[str, Inference]:
        facts = {
            "title": record["title"], "check": f"{check.id} {check.title}", "objects": record["affected_objects"],
            "rationale": record["rationale"], "value": record["value"], "risk": record["risk_reduction"],
            "effort": record["effort"], "remediation": record["remediation"]["type"],
            "autonomy": record["remediation"]["autonomy"],
        }
        provider = self.provider or TemplateProvider(renderer=lambda system, data: self._template_narrative(facts))
        text = provider.complete(NARRATIVE_SYSTEM, fence_untrusted(canonical_json(facts), "facts"))
        text = " ".join(str(text).split())
        inf = Inference(
            kind="narrative", subject_type="suggestion", subject_id=record["id"], output=text,
            confidence=record["confidence"], rationale=f"{record['rationale']} | Confidence: {conf_rationale}",
            model_id=provider.model_id, prompt_template=PROMPT_TEMPLATE, provider=provider.name,
            inputs_ref=f"{record['snapshot_id']}#{','.join(e['id'] for e in ev)}",
        )
        return text, inf

    def _template_narrative(self, facts: dict) -> str:
        parts = [f"{facts['title']}.", facts["rationale"]]
        v = facts["value"]["annualised_usd"]
        if v:
            parts.append(f"Estimated value {self.usd(v['p50'])} per year (conservative {self.usd(v['conservative'])}), "
                         f"method: {facts['value']['method']}.")
        if facts["risk"]:
            r = facts["risk"]
            parts.append(f"Risk score {r['score']} (likelihood {r['likelihood']} × impact {r['impact']}) falls to "
                         f"{r['residual_score']} once remediated.")
        parts.append(f"Effort {facts['effort']['size']} (~{facts['effort']['hours_p50']:.0f} h); the {facts['remediation']} "
                     f"draft runs at autonomy {facts['autonomy']} with a tested rollback.")
        return " ".join(parts)

    # ---------------------------------------------------------------- prioritisation
    def _prioritise(self, details: list[SuggestionDetail]) -> None:
        hv = float(self.rubrics.get("rubric.diagnostics.priority.high_value_usd"))
        hr = float(self.rubrics.get("rubric.diagnostics.priority.high_risk_score"))
        le = float(self.rubrics.get("rubric.diagnostics.priority.low_effort_hours_max"))
        upr = float(self.rubrics.get("rubric.diagnostics.priority.usd_per_risk_point"))
        for d in details:
            rec = d.record
            usd = float((rec["value"]["annualised_usd"] or {}).get("p50", 0))
            risk = rec["risk_reduction"]
            risk_pts = float(risk["score"] - risk["residual_score"]) if risk else 0.0
            high_value = usd >= hv or (risk is not None and float(risk["score"]) >= hr)
            low_effort = float(rec["effort"]["hours_p50"]) <= le
            rec["priority"]["quadrant"] = (
                "quick_win" if high_value and low_effort else
                "strategic" if high_value else
                "hygiene" if low_effort else "defer"
            )
            d.priority_score = round((usd + risk_pts * upr) / float(rec["effort"]["hours_p50"]) * rec["confidence"], 4)
        ordered = sorted(details, key=lambda d: (-d.priority_score, d.id))
        for i, d in enumerate(ordered, 1):
            d.record["priority"]["rank"] = i

    # ---------------------------------------------------------------- assumptions (savings model)
    def _assumptions(self, ctx: SnapshotContext) -> list[dict]:
        out = [
            {"name": "contract_price_per_credit", "value": ctx.price_per_credit, "unit": "USD/credit",
             "source": "CLIENT_INPUTS" if ctx.price_source == "client_input" else "rubric.diagnostics.pricing.default_price_per_credit"},
            {"name": "storage_price_per_tb_month", "value": ctx.storage_price_per_tb_month, "unit": "USD/TB-month",
             "source": "CLIENT_INPUTS" if ctx.storage_price_source == "client_input"
             else "rubric.diagnostics.pricing.default_storage_price_per_tb_month"},
            {"name": "window_start", "value": ctx.window_start.date().isoformat(), "unit": "date", "source": "snapshot"},
            {"name": "window_end", "value": ctx.window_end.date().isoformat(), "unit": "date", "source": "snapshot"},
            {"name": "window_days", "value": ctx.window_days, "unit": "days", "source": "snapshot"},
            {"name": "annualisation_factor", "value": round(ctx.annualise, 6), "unit": "x",
             "source": "rubric.diagnostics.units.days_per_year / window_days"},
        ]
        refs: set[str] = set()
        for c in self.catalogue.checks:
            refs.update(c.raw["value"].get("factors", {}).values())
            for spec in c.detector.get("params", {}).values():
                if "threshold_ref" in spec:
                    refs.add(spec["threshold_ref"])
        for ref in sorted(refs):
            out.append({"name": ref, "value": self.rubrics.get(ref), "unit": "", "source": "rubric"})
        return out


def run(snapshot: Snapshot | str | Path, tier: str = "D2", rubrics: RubricSet | None = None,
        provider: Provider | None = None) -> DiagnosticResult:
    return DiagnosticsEngine(rubrics=rubrics, provider=provider).run(snapshot, tier=tier)

