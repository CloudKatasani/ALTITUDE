"""In-boundary validation engine: executes a suite's L0-L5 checks against a source and a target endpoint.

Guarantees:
- normalisation rules (data) are applied identically on both sides before aggregation/hashing;
- ``validation_run`` rows hold aggregates only (counts, sums, deltas, flags) — never row values;
- mismatch keys are written to a local in-boundary file referenced by ``mismatch_key_ref``;
- thresholds come from the tier's rubric reference; results are reproducible for the same
  data, suite, normalisation version and rubric version (deterministic ids, no randomness).
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from altitude.core import audit
from altitude.core.ids import content_hash, stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import ValidationKnowledge, default_knowledge
from .endpoint import Endpoint
from .normalise import ColumnPlan, encode, family, row_expr, scale_of, unify
from .suite import Suite, persist_suite
from .triage import WILDCARD, Cluster, Triage, classify, record_clusters

ROW_SIGNATURES = {"duplicate_rows", "missing_rows", "extra_rows"}


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _qt(table: str) -> str:
    return ".".join(_q(p.strip('"')) for p in table.split("."))


def _cell(v: Any) -> Any:
    from altitude.patterns.golden import norm_cell

    return norm_cell(v)


@dataclass
class LevelResult:
    level: str
    result: str
    metrics: dict
    run_id: str = ""
    mismatch_key_ref: str | None = None
    clusters: list[Cluster] = field(default_factory=list)


@dataclass
class RunResult:
    suite: Suite
    levels: dict[str, LevelResult]

    @property
    def status(self) -> str:
        results = {lr.result for lr in self.levels.values()}
        if "fail" in results:
            return "fail"
        return "accepted_deviation" if "accepted_deviation" in results else "pass"

    @property
    def clusters(self) -> list[Cluster]:
        return [c for lr in self.levels.values() for c in lr.clusters]

    def cluster_for(self, known_issue_id: str) -> list[Cluster]:
        return [c for c in self.clusters if c.known_issue_id == known_issue_id]


class ValidationEngine:
    def __init__(self, store, source: Endpoint, target: Endpoint, mismatch_dir: str | Path,
                 rubrics: RubricSet | None = None, knowledge: ValidationKnowledge | None = None,
                 executed_in: str = "client_agent"):
        self.store = store
        self.source = source
        self.target = target
        self.mismatch_dir = Path(mismatch_dir)
        self.rubrics = rubrics or default_rubrics()
        self.knowledge = knowledge or default_knowledge()
        self.executed_in = executed_in

    # ================================================================== public
    def run(self, suite: Suite, run_label: str = "run-1", as_of: date | None = None, now: datetime | None = None,
            timings: list[dict] | None = None, actor: str = "validation-engine") -> RunResult:
        spec = suite.spec
        as_of = as_of or date.today()
        now = (now or datetime.now(timezone.utc)).replace(tzinfo=None)
        th = self.rubrics.get(suite.threshold_ref)
        triage = Triage(self.knowledge, self.rubrics, spec.source_dialect, spec.object_id)
        persist_suite(self.store, suite, now)

        src_cols = self.source.columns(spec.source_table)
        tgt_cols = self.target.columns(spec.target_table)
        if not src_cols or not tgt_cols:
            missing = spec.source_table if not src_cols else spec.target_table
            raise ValueError(f"table {missing} not found on {'source' if not src_cols else 'target'} endpoint")
        plans = self._plans(suite, src_cols, tgt_cols)
        results: dict[str, LevelResult] = {}
        files: dict[str, list[dict]] = {}

        for level in suite.active_levels:
            checks = suite.checks_for(level)
            mode = checks[0].mode
            if level == "L0":
                results[level] = self._l0(src_cols, tgt_cols, th, triage)
            elif level == "L1":
                results[level] = self._l1(suite, plans, th)
            elif level == "L2":
                results[level] = self._l2(suite, plans, th, mode)
            elif level == "L3":
                results[level], files[level] = self._l3(suite, plans, th, mode, triage)
            elif level == "L4":
                results[level], files[level] = self._l4(suite, th, triage)
            elif level == "L5":
                results[level] = self._l5(suite, th, timings)
            results[level].metrics.update({"mode": mode, "tier": suite.tier, "run_label": run_label,
                                           "thresholds": {k: v for k, v in th.items()
                                                          if k.startswith(level.lower() + "_")}})

        run_ids = {lv: stable_id("VR", suite.suite_id, lv, run_label, content_hash(r.metrics, 16))
                   for lv, r in results.items()}
        refs = {lv: self._write_mismatch_file(suite, lv, run_label, rows) for lv, rows in files.items() if rows}
        totals = {lv: int(r.metrics.get("mismatches", r.metrics.get("diff_rows", 0)) or 0) for lv, r in results.items()}
        clusters = triage.clusters(run_ids, totals)
        self._attribute(results, clusters, run_ids)

        active = self._active_deviations(spec.object_id, as_of)
        for lv, r in results.items():
            r.run_id = run_ids[lv]
            r.mismatch_key_ref = refs.get(lv)
            r.clusters = [c for c in clusters if c.level == lv] + r.clusters
            if r.result == "fail" and r.clusters and all(c.signature_key in active for c in r.clusters):
                r.result = "accepted_deviation"
                r.metrics["accepted_deviations"] = sorted({active[c.signature_key] for c in r.clusters})

        for lv, r in results.items():
            if self.store.get("validation_run", run_id=r.run_id):
                continue
            self.store.insert("validation_run", {
                "run_id": r.run_id, "suite_id": suite.suite_id, "object_id": spec.object_id, "level": lv,
                "normalisation_rule_version": suite.normaliser.version,
                "threshold_rubric_version": self.rubrics.version, "result": r.result, "metrics": r.metrics,
                "mismatch_key_ref": r.mismatch_key_ref, "executed_in": self.executed_in, "completed_at": now,
            })
        primary = [c for c in clusters if not c.rationale.startswith("Explained by")]
        record_clusters(self.store, primary, run_ids, refs, self.rubrics)
        for c in [c for lr in results.values() for c in lr.clusters if c not in primary]:
            if not self.store.get("mismatch_cluster", cluster_id=c.cluster_id):
                self.store.insert("mismatch_cluster", {
                    "cluster_id": c.cluster_id, "run_id": run_ids[c.level], "signature": c.signature_key,
                    "known_issue_id": c.known_issue_id, "mismatch_count": c.count, "confidence": c.confidence,
                    "rationale": c.rationale})
        audit.record(self.store, actor, "validation.run", actor_type="agent", subject_type="validation_suite",
                     subject_id=suite.suite_id, details={"run_label": run_label,
                                                         "results": {lv: r.result for lv, r in results.items()}})
        return RunResult(suite, results)

    # ================================================================== helpers
    def _plans(self, suite: Suite, src_cols, tgt_cols) -> list[ColumnPlan]:
        tgt = {c[0].lower(): c for c in tgt_cols}
        wanted = {c.lower() for c in suite.spec.columns} if suite.spec.columns else None
        plans = []
        for name, stype, _ in src_cols:
            if name.lower() not in tgt or (wanted is not None and name.lower() not in wanted):
                continue
            ttype = tgt[name.lower()][1]
            fam = unify(family(stype), family(ttype))
            plans.append(ColumnPlan(name, stype, ttype, fam, max(scale_of(stype), scale_of(ttype))))
        for k in suite.spec.key_columns:
            if k.lower() not in {p.name.lower() for p in plans}:
                raise ValueError(f"key column {k} missing on one side of {suite.spec.object_id}")
        return plans

    def _tables(self, suite: Suite) -> tuple[str, str]:
        return _qt(suite.spec.source_table), _qt(suite.spec.target_table)

    def _both(self, sql_src: str, sql_tgt: str, params_s=None, params_t=None):
        return self.source.query(sql_src, params_s), self.target.query(sql_tgt, params_t)

    # ------------------------------------------------------------------ L0
    def _l0(self, src_cols, tgt_cols, th, triage: Triage) -> LevelResult:
        tgt = {c[0].lower(): c for c in tgt_cols}
        src = {c[0].lower(): c for c in src_cols}
        missing = sorted(n for n in src if n not in tgt)
        extra = sorted(n for n in tgt if n not in src)
        problems, nullability = [], 0
        for n in sorted(set(src) & set(tgt)):
            (_, st, sn), (_, tt, tn) = src[n], tgt[n]
            fs, ft = family(st), family(tt)
            problem = None
            if fs == ft or {fs, ft} <= {"integer", "decimal"}:
                if fs in ("integer", "decimal") and scale_of(tt) < scale_of(st):
                    problem = "scale_reduced"
            elif fs == "timestamp" and ft == "date":
                problem = "time_component_dropped"
            elif fs == "date" and ft == "timestamp":
                problem = None
            elif {fs, ft} <= {"float", "decimal", "integer"}:
                problem = "approximate_numeric"
            else:
                problem = "type_family_changed"
            if problem:
                problems.append({"column": n, "source_type": st, "target_type": tt, "problem": problem})
                sig = {"scale_reduced": "scale_truncation", "time_component_dropped": "time_component_lost"}.get(
                    problem, "unexplained")
                triage.observe("L0", sig, n)
            if (not sn) and tn:
                nullability += 1
        for n in missing:
            triage.observe("L0", "unexplained", n)
        ok = not missing and len(problems) <= int(th["l0_type_mismatch_max"])
        return LevelResult("L0", "pass" if ok else "fail", {
            "columns_source": len(src), "columns_target": len(tgt), "missing_in_target": missing,
            "extra_in_target": extra, "type_mismatches": problems, "nullability_relaxed": nullability,
            "mismatches": len(missing) + len(problems)})

    # ------------------------------------------------------------------ L1
    def _l1(self, suite: Suite, plans, th) -> LevelResult:
        s_tbl, t_tbl = self._tables(suite)
        (_, rs), (_, rt) = self._both(f"SELECT count(*) FROM {s_tbl}", f"SELECT count(*) FROM {t_tbl}")
        ns, nt = int(rs[0][0]), int(rt[0][0])
        limit = int(th["l1_count_delta_max"])
        metrics: dict[str, Any] = {"source_rows": ns, "target_rows": nt, "delta": nt - ns}
        ok = abs(nt - ns) <= limit
        pc = suite.spec.partition_column
        if pc:
            plan = next(p for p in plans if p.name.lower() == pc.lower())
            expr = suite.normaliser.canonical_expr(plan)
            sql = "SELECT {e} AS p, count(*) AS n FROM {t} GROUP BY 1"
            (_, ps), (_, pt) = self._both(sql.format(e=expr, t=s_tbl), sql.format(e=expr, t=t_tbl))
            ds, dt = dict(ps), dict(pt)
            bad = sorted(k for k in set(ds) | set(dt) if abs(int(dt.get(k, 0)) - int(ds.get(k, 0))) > limit)
            metrics.update({"partitions_compared": len(set(ds) | set(dt)), "partitions_mismatched": len(bad)})
            ok = ok and not bad
        metrics["mismatches"] = abs(nt - ns)
        return LevelResult("L1", "pass" if ok else "fail", metrics)

    # ------------------------------------------------------------------ L2
    def _l2(self, suite: Suite, plans, th, mode: str) -> LevelResult:
        s_tbl, t_tbl = self._tables(suite)
        norm = suite.normaliser
        where, sampled = "", False
        pc = suite.spec.partition_column
        if mode == "sample" and pc:
            plan = next(p for p in plans if p.name.lower() == pc.lower())
            pexpr = norm.canonical_expr(plan)
            n = int(self.rubrics.get("rubric.validation.sampling.l2_sample_partitions"))
            _, parts = self.source.query(f"SELECT DISTINCT {pexpr} AS p FROM {s_tbl} ORDER BY 1 DESC LIMIT {n}")
            vals = [p[0] for p in parts]
            if vals:
                where = f" WHERE {pexpr} IN ({', '.join('?' for _ in vals)})"
                sampled = True
        aggs, meta = ["count(*)"], []
        for p in plans:
            c = norm.canonical_expr(p)
            v = norm.value_expr(_q(p.name), p.family)
            aggs += [f"count({c})", f"count(DISTINCT {c})", f"min({c})", f"max({c})"]
            meta += [(p.name, "non_null"), (p.name, "distinct"), (p.name, "min"), (p.name, "max")]
            if p.family in ("integer", "decimal"):
                aggs.append(f"sum(CAST({v} AS DECIMAL(38, {p.scale})))")
                meta.append((p.name, "sum"))
            elif p.family == "float":
                aggs.append(f"sum(CAST({v} AS DOUBLE))")
                meta.append((p.name, "sum_float"))
            elif p.family == "string":
                aggs.append(f"sum(length({c}))")
                meta.append((p.name, "total_length"))
        sql = "SELECT " + ", ".join(aggs) + " FROM {t}" + where
        params = vals if sampled else None
        (_, rs), (_, rt) = self._both(sql.format(t=s_tbl), sql.format(t=t_tbl), params, params)
        s_row, t_row = rs[0], rt[0]
        mism = []
        num_tol = float(th["l2_numeric_rel_tolerance"])
        flt_tol = float(th["l2_float_rel_tolerance"])
        for (col, metric), sv, tv in zip(meta, s_row[1:], t_row[1:]):
            if metric in ("sum", "sum_float"):
                tol = flt_tol if metric == "sum_float" else num_tol
                a, b = float(sv or 0), float(tv or 0)
                same = math.isclose(a, b, rel_tol=tol, abs_tol=0.0) if tol else (sv or 0) == (tv or 0)
                if not same:
                    mism.append({"column": col, "metric": metric,
                                 "rel_delta": round(abs(a - b) / max(abs(a), abs(b)), 12) if (a or b) else 0.0})
            elif sv != tv:
                entry = {"column": col, "metric": metric}
                if metric in ("non_null", "distinct", "total_length"):
                    entry.update({"source": sv, "target": tv})
                mism.append(entry)
        metrics = {"source_rows": s_row[0], "target_rows": t_row[0], "columns_compared": len(plans),
                   "metric_mismatches": mism, "mismatches": len(mism), "sampled_partitions": sampled}
        ok = not mism and s_row[0] == t_row[0]
        return LevelResult("L2", "pass" if ok else "fail", metrics)

    # ------------------------------------------------------------------ L3
    def _key_expr(self, suite: Suite, plans) -> str:
        keyset = {k.lower() for k in suite.spec.key_columns}
        kp = [p for p in plans if p.name.lower() in keyset]
        kp.sort(key=lambda p: [k.lower() for k in suite.spec.key_columns].index(p.name.lower()))
        return " || ".join(encode(suite.normaliser.canonical_expr(p)) for p in kp)

    def _l3(self, suite: Suite, plans, th, mode: str, triage: Triage) -> tuple[LevelResult, list[dict]]:
        s_tbl, t_tbl = self._tables(suite)
        kexpr, rexpr = self._key_expr(suite, plans), row_expr(suite.normaliser, plans)
        sql = f"SELECT {kexpr} AS k, md5({rexpr}) AS h FROM {{t}}"
        (_, rs), (_, rt) = self._both(sql.format(t=s_tbl), sql.format(t=t_tbl))
        src, tgt = defaultdict(list), defaultdict(list)
        for k, h in rs:
            src[k].append(h)
        for k, h in rt:
            tgt[k].append(h)
        keys = sorted(set(src) | set(tgt))
        if mode == "sample":
            rate = float(self.rubrics.get("rubric.validation.sampling.l3_sample_rate"))
            keys = [k for k in keys if int(hashlib.md5(k.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF < rate]
        cats: dict[str, str] = {}
        for k in keys:
            s, t = src.get(k, []), tgt.get(k, [])
            if not t:
                cats[k] = "missing_rows"
            elif not s:
                cats[k] = "extra_rows"
            elif len(s) != len(t):
                cats[k] = "duplicate_rows" if set(s) == set(t) else "duplicate_conflict"
            elif sorted(s) != sorted(t):
                cats[k] = "hash_mismatch"
        counts = Counter(cats.values())
        for k, cat in cats.items():
            if cat in ROW_SIGNATURES:
                n = abs(len(tgt.get(k, [])) - len(src.get(k, []))) if cat == "duplicate_rows" else 1
                triage.observe("L3", cat, WILDCARD, n)
            elif cat == "duplicate_conflict":
                triage.observe("L3", "unexplained", WILDCARD)
        mismatched = [k for k, c in sorted(cats.items()) if c == "hash_mismatch"]
        inspected = mismatched[: int(self.rubrics.get("rubric.validation.triage.max_keys_inspected"))]
        if inspected:
            self._column_signatures(suite, plans, kexpr, inspected, triage, th)
        n_keys = len(keys)
        total = len(cats)
        rate = total / n_keys if n_keys else 0.0
        ok = total <= int(th["l3_mismatch_max"]) and rate <= float(th["l3_mismatch_rate_max"])
        metrics = {"keys_compared": n_keys, "source_rows": len(rs), "target_rows": len(rt),
                   "mismatches": total, "mismatch_rate": round(rate, 9),
                   "by_category": dict(sorted(counts.items())), "keys_inspected_for_triage": len(inspected),
                   "sampled": mode == "sample"}
        rows = [{"key": k, "category": c} for k, c in sorted(cats.items())]
        return LevelResult("L3", "pass" if ok else "fail", metrics), rows

    def _column_signatures(self, suite: Suite, plans, kexpr: str, keys: list[str], triage: Triage, th) -> None:
        s_tbl, t_tbl = self._tables(suite)
        norm = suite.normaliser
        cols = ", ".join(f"{_q(p.name)} AS c{i}, {norm.canonical_expr(p)} AS n{i}" for i, p in enumerate(plans))
        marks = ", ".join("?" for _ in keys)
        sql = f"SELECT {kexpr} AS k, {cols} FROM {{t}} WHERE {kexpr} IN ({marks})"
        (_, rs), (_, rt) = self._both(sql.format(t=s_tbl), sql.format(t=t_tbl), keys, keys)
        by_s = {r[0]: r for r in rs}
        by_t = {r[0]: r for r in rt}
        for k in keys:
            s, t = by_s.get(k), by_t.get(k)
            if s is None or t is None:
                continue
            for i, p in enumerate(plans):
                raw_s, can_s = s[1 + 2 * i], s[2 + 2 * i]
                raw_t, can_t = t[1 + 2 * i], t[2 + 2 * i]
                if can_s != can_t:
                    triage.observe("L3", classify(raw_s, raw_t, self.rubrics), p.name)

    # ------------------------------------------------------------------ L4
    def _l4(self, suite: Suite, th, triage: Triage) -> tuple[LevelResult, list[dict]]:
        tol = float(th["l4_numeric_rel_tolerance"])
        limit = int(th["l4_diff_rows_max"])
        per_query, diff_rows, total = [], [], 0
        ok = True
        for q in suite.spec.queries:
            (cs, rs), (ct, rt) = self._both(q.source_sql, q.target_sql or q.source_sql)
            s = [tuple(_cell(v) for v in r) for r in rs]
            t = [tuple(_cell(v) for v in r) for r in rt]
            only_s, only_t = _multiset_diff(s, t, tol)
            n = len(only_s) + len(only_t)
            total += n
            if n > limit:
                ok = False
            if n:
                triage.observe("L4", _result_signature(s, t, tol), q.id, n)
                diff_rows += [{"query_id": q.id, "side": "source", "row": [_json(v) for v in r]} for r in only_s]
                diff_rows += [{"query_id": q.id, "side": "target", "row": [_json(v) for v in r]} for r in only_t]
            per_query.append({"query_id": q.id, "source_rows": len(s), "target_rows": len(t), "diff_rows": n})
        return LevelResult("L4", "pass" if ok else "fail", {"queries": per_query, "diff_rows": total,
                                                            "mismatches": total}), diff_rows

    # ------------------------------------------------------------------ L5
    def _l5(self, suite: Suite, th, timings: list[dict] | None) -> LevelResult:
        from .suite import PerfSpec

        perf = [PerfSpec(**t) for t in timings] if timings else suite.spec.perf
        p50_max, p95_max = float(th["l5_p50_ratio_max"]), float(th["l5_p95_ratio_max"])
        out, ok = [], True
        for p in perf:
            r50 = p.target_p50_ms / p.baseline_p50_ms if p.baseline_p50_ms else math.inf
            r95 = p.target_p95_ms / p.baseline_p95_ms if p.baseline_p95_ms else math.inf
            sla_ok = p.sla_p95_ms is None or p.target_p95_ms <= p.sla_p95_ms
            q_ok = r50 <= p50_max and r95 <= p95_max and sla_ok
            ok = ok and q_ok
            out.append({"query_id": p.query_id, "p50_ratio": round(r50, 4), "p95_ratio": round(r95, 4),
                        "sla_met": sla_ok, "result": "pass" if q_ok else "fail"})
        failing = sum(1 for o in out if o["result"] == "fail")
        return LevelResult("L5", "pass" if ok else "fail", {"queries": out, "mismatches": failing})

    # ------------------------------------------------------------------ attribution & deviations
    def _attribute(self, results: dict[str, LevelResult], clusters: list[Cluster], run_ids: dict[str, str]) -> None:
        """Link L1/L2 failures to the L3 root-cause clusters that explain them."""
        l3 = [c for c in clusters if c.level == "L3"]
        for lv in ("L1", "L2"):
            r = results.get(lv)
            if r is None or r.result != "fail":
                continue
            if lv == "L1":
                explaining = [c for c in l3 if c.signature in ROW_SIGNATURES]
                cols = [WILDCARD]
            else:
                cols = sorted({m["column"] for m in r.metrics["metric_mismatches"]})
                explaining = [c for c in l3 if c.column == WILDCARD or c.column in cols]
            unexplained_cols = [col for col in cols if not any(c.column in (col, WILDCARD) for c in explaining)]
            for c in explaining:
                r.clusters.append(self._mirror(c, lv, run_ids))
            for col in unexplained_cols if lv == "L2" else ([] if explaining else [WILDCARD]):
                sig = self.knowledge.signatures["unexplained"]
                conf = round(float(self.rubrics.get(sig.confidence_ref)), 3)
                rationale = (f"{lv} difference on {col} is not explained by an L3 root-cause cluster"
                             f"{'' if 'L3' in results else ' (L3 not run for this tier)'}; human triage required.")
                r.clusters.append(Cluster(lv, "unexplained", col, 1, 1, None, None, conf, rationale,
                                          stable_id("MMC", run_ids[lv], lv, "unexplained", col)))

    def _mirror(self, c: Cluster, level: str, run_ids: dict[str, str]) -> Cluster:
        return Cluster(level, c.signature, c.column, c.count, c.total, c.known_issue_id, c.fix_pattern_id,
                       c.confidence, f"Explained by L3 cluster {c.cluster_id}: {c.rationale}",
                       stable_id("MMC", run_ids[level], level, c.signature, c.column))

    def _active_deviations(self, object_id: str, as_of: date) -> dict[str, str]:
        rows = self.store.query(
            "SELECT s.signature, d.deviation_id FROM accepted_deviation d "
            "JOIN accepted_deviation_scope s ON s.deviation_id = d.deviation_id "
            "WHERE s.object_id = ? AND d.review_by >= ? ORDER BY d.approved_at, d.deviation_id", [object_id, as_of])
        active: dict[str, str] = {}
        for r in rows:
            active.setdefault(r["signature"], r["deviation_id"])
        return active

    def _write_mismatch_file(self, suite: Suite, level: str, run_label: str, rows: list[dict]) -> str:
        self.mismatch_dir.mkdir(parents=True, exist_ok=True)
        path = self.mismatch_dir / f"{suite.suite_id}.{level}.{run_label}.mismatch_keys.jsonl"
        body = "".join(json.dumps(r, sort_keys=True, default=str) + "\n" for r in rows)
        path.write_text(body)
        digest = hashlib.sha256(body.encode()).hexdigest()[:16]
        return f"file://{path.resolve()}#sha256={digest}"


# --------------------------------------------------------------------------- L4 helpers


def _json(v: Any) -> Any:
    return v if isinstance(v, (int, float, str, bool)) or v is None else str(v)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _multiset_diff(s: list[tuple], t: list[tuple], tol: float) -> tuple[list[tuple], list[tuple]]:
    cs, ct = Counter(s), Counter(t)
    only_s = sorted((cs - ct).elements(), key=repr)
    only_t = sorted((ct - cs).elements(), key=repr)
    if tol and only_s and len(only_s) == len(only_t):
        def key(r):
            return tuple(repr(v) for v in r if not _is_num(v))
        a, b = sorted(only_s, key=key), sorted(only_t, key=key)
        if all(key(x) == key(y) and all(
                (math.isclose(float(u), float(w), rel_tol=tol) if _is_num(u) and _is_num(w) else u == w)
                for u, w in zip(x, y)) for x, y in zip(a, b)):
            return [], []
    return only_s, only_t


def _transform(rows: list[tuple], f) -> list[tuple]:
    return [tuple(f(v) if isinstance(v, str) else v for v in r) for r in rows]


def _reaggregate(rows: list[tuple]) -> Counter:
    groups: dict[tuple, list] = {}
    for r in rows:
        k = tuple(v for v in r if not _is_num(v))
        nums = [v for v in r if _is_num(v)]
        acc = groups.setdefault(k, [0] * len(nums))
        for i, v in enumerate(nums):
            acc[i] += v
    return Counter({k: 1 for k in ((k, tuple(v)) for k, v in groups.items())})


def _result_signature(s: list[tuple], t: list[tuple], tol: float) -> str:
    transforms = [
        ("trailing_space", lambda v: v.rstrip(" ")),
        ("case_only", lambda v: v.upper()),
        ("empty_vs_null", lambda v: None if v == "" else v),
    ]
    for sig, f in transforms:
        ts, tt = _transform(s, f), _transform(t, f)
        if Counter(ts) == Counter(tt) or _reaggregate(ts) == _reaggregate(tt):
            return sig
    return "unexplained"
