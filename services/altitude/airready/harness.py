"""Evaluation harness for the semantic layer and Cortex Agents (Section 15.2 AI pack / 19.2 step 4).

Golden questions (``knowledge/airready/golden_questions.yaml``) carry an expected KPI, dimensions, SQL and
answer over a small fixture. A candidate answer function maps a question to ``{"sql": ...}`` or
``{"refuse": True}``; its SQL is executed on the fixture and scored on answer equivalence
(order-insensitive, numeric tolerance from the rubric). Out-of-scope questions must be refused.

The default candidate is :class:`SemanticCompiler`, a deterministic, offline compiler from question text to
SQL over the certified KPI registry — the baseline a Cortex Agent must match before it is exposed.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import duckdb

from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics

from . import kpi_registry
from .kpi_registry import Registry, norm, snake

GOLDEN = "airready/golden_questions.yaml"


def load_golden(root: Path | None = None) -> dict:
    return load_yaml(GOLDEN, root)


# --------------------------------------------------------------------------- fixture
def fixture_connection(golden: dict) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    catalogs: set[str] = set()
    schemas: set[str] = set()
    for f in golden["fixtures"]:
        db, sch, _ = f["table"].split(".")
        if db not in catalogs:
            con.execute(f'ATTACH \':memory:\' AS "{db}"')
            catalogs.add(db)
        if (db, sch) not in schemas:
            con.execute(f'CREATE SCHEMA "{db}"."{sch}"')
            schemas.add((db, sch))
        cols = f["columns"]
        con.execute(f"CREATE TABLE {f['table']} (" + ", ".join(f'"{c}" {t}' for c, t in cols.items()) + ")")
        if f["rows"]:
            con.executemany(f"INSERT INTO {f['table']} VALUES (" + ", ".join("?" for _ in cols) + ")", f["rows"])
    return con


def _norm_value(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    return v if v is None else str(v)


def _norm_rows(rows: list, tol: float) -> list[tuple]:
    def key(row: tuple) -> str:
        return repr(tuple(round(x / tol) if isinstance(x, float) and tol else x for x in row))
    return sorted((tuple(_norm_value(v) for v in r) for r in rows), key=key)


def answers_match(actual: list, expected: list, tol: float) -> bool:
    a, e = _norm_rows(actual, tol), _norm_rows(expected, tol)
    if len(a) != len(e):
        return False
    for ra, re_ in zip(a, e):
        if len(ra) != len(re_):
            return False
        for x, y in zip(ra, re_):
            if isinstance(x, float) and isinstance(y, float):
                if abs(x - y) > tol:
                    return False
            elif x != y:
                return False
    return True


# --------------------------------------------------------------------------- default candidate
@dataclass
class CompiledQuery:
    kpi_id: str
    dimensions: list[str]
    sql: str


def _phrase_in(phrase: str, text: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


class SemanticCompiler:
    """Question text -> SQL over the certified registry (KPI by longest name/synonym match, dimensions by
    name/synonym within the KPI's domain, joins along declared relationships). Refuses when ungrounded."""

    def __init__(self, registry: Registry | None = None):
        self.registry = registry or kpi_registry.load()

    def _kpi(self, text: str) -> dict | None:
        best: tuple[int, dict] | None = None
        for k in self.registry.doc["kpis"]:
            if not k["certified"]:
                continue
            for label in [k["name"], *k["synonyms"]]:
                p = norm(label)
                if _phrase_in(p, text) and (best is None or len(p) > best[0]):
                    best = (len(p), k)
        return best[1] if best else None

    def compile(self, question: str) -> CompiledQuery | None:
        text = norm(question)
        kpi = self._kpi(text)
        if kpi is None:
            return None
        claimed = {norm(x) for x in [kpi["name"], *kpi["synonyms"]] if _phrase_in(norm(x), text)}
        rest = text
        for c in sorted(claimed, key=len, reverse=True):
            rest = re.sub(rf"(?<![a-z0-9]){re.escape(c)}(?![a-z0-9])", " ", rest)
        domain = self.registry.domains[kpi["domain"]]
        dims: list[dict] = []
        for m in domain["dimensions"]:
            labels = sorted({norm(m["name"].replace("_", " ")), *(norm(s) for s in m.get("synonyms", []))}, key=len,
                            reverse=True)
            if any(_phrase_in(lbl, rest) for lbl in labels):
                dims.append(m)
        base = kpi["table"]
        aliases = {t["alias"]: t for t in domain["tables"]}
        joins: list[str] = []
        needed = sorted({m["table"] for m in dims} - {base})
        for alias in needed:
            rel = next((r for r in domain["relationships"] if {r["from"], r["to"]} == {base, alias}), None)
            if rel is None:
                return None
            to_pk = aliases[rel["to"]]["primary_key"]
            cond = " AND ".join(f"{rel['from']}.{c} = {rel['to']}.{p}" for c, p in zip(rel["columns"], to_pk))
            joins.append(f"LEFT JOIN {aliases[alias]['table']} AS {alias} ON {cond}")
        metric = self.registry.translate(kpi["domain"], kpi["expression"])
        select = [f"{m['table']}.{m['expr']} AS {m['name']}" for m in dims] + [f"{metric} AS {snake(kpi['name'])}"]
        sql = f"SELECT {', '.join(select)} FROM {aliases[base]['table']} AS {base}"
        if joins:
            sql += " " + " ".join(joins)
        if dims:
            sql += " GROUP BY " + ", ".join(f"{m['table']}.{m['expr']}" for m in dims)
        return CompiledQuery(kpi["id"], [m["name"] for m in dims], sql)

    def __call__(self, question: str) -> dict:
        q = self.compile(question)
        if q is None:
            return {"refuse": True, "reason": "no certified KPI in the registry matches the question"}
        return {"sql": q.sql, "kpi": q.kpi_id, "dimensions": q.dimensions}


# --------------------------------------------------------------------------- harness
@dataclass
class QuestionResult:
    question_id: str
    question: str
    passed: bool
    candidate: dict
    actual: list = field(default_factory=list)
    reason: str = ""


@dataclass
class HarnessReport:
    results: list[QuestionResult]
    score: float
    pass_rate_min: float
    golden_integrity: list[str]

    @property
    def passed(self) -> bool:
        return self.score >= self.pass_rate_min and not self.golden_integrity

    def to_dict(self) -> dict:
        from altitude.core.store import json_safe

        return {**json_safe(asdict(self)), "passed": self.passed}


def check_golden(golden: dict, con: duckdb.DuckDBPyConnection, tol: float) -> list[str]:
    """Every expected SQL must reproduce its recorded expected answer on the fixture."""
    problems = []
    for q in golden["questions"]:
        exp = q["expected"]
        if exp.get("refuse"):
            continue
        rows = con.execute(exp["sql"]).fetchall()
        if not answers_match(rows, exp["answer"], tol):
            problems.append(f"{q['id']}: expected SQL returns {rows}, not the recorded answer {exp['answer']}")
    return problems


def run(answer_fn: Callable[[str], dict] | None = None, golden: dict | None = None,
        registry: Registry | None = None, rubrics: RubricSet | None = None) -> HarnessReport:
    rubrics = rubrics or default_rubrics()
    golden = golden or load_golden()
    answer_fn = answer_fn or SemanticCompiler(registry)
    tol = float(rubrics.get("rubric.airready.eval.numeric_tolerance"))
    con = fixture_connection(golden)
    integrity = check_golden(golden, con, tol)
    results = []
    for q in golden["questions"]:
        exp = q["expected"]
        cand = answer_fn(q["question"])
        if exp.get("refuse"):
            ok = bool(cand.get("refuse"))
            results.append(QuestionResult(q["id"], q["question"], ok, cand,
                                          reason="" if ok else "answered an out-of-scope question"))
            continue
        if cand.get("refuse") or not cand.get("sql"):
            results.append(QuestionResult(q["id"], q["question"], False, cand, reason="refused an answerable question"))
            continue
        try:
            rows = con.execute(cand["sql"]).fetchall()
        except duckdb.Error as e:
            results.append(QuestionResult(q["id"], q["question"], False, cand, reason=f"SQL failed: {e}"))
            continue
        ok = answers_match(rows, exp["answer"], tol)
        results.append(QuestionResult(q["id"], q["question"], ok, cand, [list(r) for r in rows],
                                      "" if ok else f"answer {rows} != expected {exp['answer']}"))
    score = round(sum(r.passed for r in results) / len(results), 4) if results else 0.0
    return HarnessReport(results, score, float(rubrics.get("rubric.airready.eval.pass_rate_min")), integrity)
