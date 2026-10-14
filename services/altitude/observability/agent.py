"""Ask-the-platform agent (Section 7.3): answers questions over the SEMANTIC layer, with citations.

Deterministic, offline implementation (the default ``template`` provider):

1. **Intent** — the question is matched against the certified KPI definitions in ``SEMANTIC.KPI_DEFINITIONS``
   (name + synonyms). Below ``rubric.obs.agent.min_match_score`` the agent refuses: it never answers from
   anything but a certified KPI.
2. **Slots** — account, dimension (any of the KPI's dimension values named in the question), time window
   ("yesterday", "last 7 days", "last week", "this month", "last month", ISO dates, month names) and ranking
   ("which ... most", "top").
3. **Answer** — computed from ``SEMANTIC.KPI_VALUES`` with the KPI's aggregation; no data in the window ⇒ refusal.
4. **Citations** — KPI id + definition hash, the KPI rows used, and the RAW source tables with row counts in the
   window. Every answer or refusal is recorded as an :class:`altitude.core.ai.Inference` (confidence + rationale);
   low-confidence answers enter the human review queue when a store is supplied.

The generated Cortex Agent spec (``generated/observability/cortex/ask_the_platform_agent.json``) deploys the same
contract in-account over the generated semantic views.
"""

from __future__ import annotations

import calendar
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from typing import Any

from altitude.core.ai import Inference, ReviewQueue, TemplateProvider
from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import kpi_table, load_sources
from .db import ObsDatabase

PROMPT_TEMPLATE = "obs.ask_the_platform@1.0.0"
MIN_SCORE_REF = "rubric.obs.agent.min_match_score"
DEFAULT_WINDOW_REF = "rubric.obs.agent.default_window_days"
MAX_CITATIONS_REF = "rubric.obs.agent.max_citation_rows"
CONF_FLOOR_REF = "rubric.obs.agent.confidence_floor"

STOPWORDS = {
    "a", "an", "the", "of", "by", "what", "was", "were", "is", "are", "how", "many", "much", "did", "do", "does",
    "we", "our", "us", "on", "in", "for", "at", "to", "from", "per", "and", "or", "which", "who", "whose", "me",
    "show", "tell", "give", "last", "past", "this", "previous", "yesterday", "today", "week", "weeks", "month",
    "months", "day", "days", "year", "current", "currently", "there", "have", "has", "had", "it", "its", "be",
    "most", "top", "highest", "lowest", "least", "with", "over", "during", "since", "between", "all", "any", "so",
    "far", "now", "latest", "value", "values", "number", "use", "used", "using", "get", "got",
}
MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
_WORD = re.compile(r"[a-z0-9_]+")


def tokens(text: str) -> list[str]:
    out = []
    for t in _WORD.findall(text.lower()):
        if t in STOPWORDS or t.isdigit():
            continue
        out.append(t[:-1] if t.endswith("s") and not t.endswith(("ss", "us", "is")) else t)
    return out


@dataclass
class Answer:
    question: str
    answered: bool
    text: str
    kpi_id: str | None = None
    value: float | None = None
    unit: str | None = None
    account: str | None = None
    dimension: str | None = None
    window: tuple[str, str] | None = None
    ranking: list[dict] | None = None
    citations: list[dict] = field(default_factory=list)
    confidence: float = 0.0
    rationale: str = ""
    refusal_reason: str | None = None
    inference_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class AskThePlatform:
    def __init__(self, db: ObsDatabase, rubrics: RubricSet | None = None, store: Any = None):
        self.db = db
        self.rubrics = rubrics or default_rubrics()
        self.store = store
        self.provider = TemplateProvider()
        self._defs = {r["KPI_ID"]: r for r in db.query("SELECT * FROM SEMANTIC.KPI_DEFINITIONS")} \
            if db.relation_exists("SEMANTIC", "KPI_DEFINITIONS") else {}
        self._wm = {c.table: c.watermark for c in load_sources() if c.watermark}
        self._snap = {c.table for c in load_sources() if c.is_snapshot}

    # ------------------------------------------------------------------ intent
    def match(self, question: str) -> list[tuple[float, int, str]]:
        """Candidate KPIs as ``(score, matched_tokens, kpi_id)``, best first."""
        q = set(tokens(question))
        out = []
        for kid, d in self._defs.items():
            phrases = [d["NAME"]] + json.loads(d["SYNONYMS"] or "[]")
            best, matched = 0.0, set()
            for p in phrases:
                pt = set(tokens(p))
                if not pt:
                    continue
                hit = pt & q
                if hit:
                    best = max(best, len(hit) / len(pt))
                    matched |= hit
            if best:
                tier_rank = {"core": 2, "extended": 1}.get(d["TIER"], 0)
                out.append((round(best, 4), len(matched), tier_rank, kid))
        out.sort(key=lambda x: (-x[0], -x[1], -x[2], x[3]))
        return [(s, m, k) for s, m, _, k in out]

    # ------------------------------------------------------------------ slots
    def _as_of(self, kpi_id: str) -> date | None:
        return self.db.scalar("SELECT max(PERIOD) FROM SEMANTIC.KPI_VALUES WHERE KPI_ID = ?", [kpi_id])

    def window(self, question: str, as_of: date, aggregation: str) -> tuple[date, date, str, bool]:
        """``(start, end, label, explicit)`` for the question, relative to ``as_of`` (the latest data day)."""
        q = question.lower()
        m = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s*(?:to|and|-|until)\s*(\d{4}-\d{2}-\d{2}))?", q)
        if m:
            a = date.fromisoformat(m.group(1))
            b = date.fromisoformat(m.group(2)) if m.group(2) else a
            return a, b, f"{a}..{b}", True
        m = re.search(r"(?:last|past|previous)\s+(\d+)\s+days?", q)
        if m:
            n = int(m.group(1))
            return as_of - timedelta(days=n - 1), as_of, f"last {n} days", True
        if "yesterday" in q:
            d = as_of - timedelta(days=1)
            return d, d, "yesterday", True
        if re.search(r"\btoday\b", q):
            return as_of, as_of, "today", True
        if re.search(r"(last|past|previous)\s+week", q):
            return as_of - timedelta(days=6), as_of, "last 7 days", True
        if re.search(r"(last|past|previous)\s+month", q):
            first = as_of.replace(day=1)
            prev_end = first - timedelta(days=1)
            return prev_end.replace(day=1), prev_end, f"{calendar.month_name[prev_end.month]} {prev_end.year}", True
        if re.search(r"this\s+month|month\s+to\s+date|mtd", q):
            return as_of.replace(day=1), as_of, "month to date", True
        for name, i in MONTHS.items():
            m = re.search(rf"\b{name}\b(?:\s+(\d{{4}}))?", q)
            if m:
                year = int(m.group(1)) if m.group(1) else (as_of.year if i <= as_of.month else as_of.year - 1)
                start = date(year, i, 1)
                end = date(year, i, calendar.monthrange(year, i)[1])
                return start, end, f"{calendar.month_name[i]} {year}", True
        if aggregation == "latest":
            return as_of, as_of, "latest", False
        n = int(self.rubrics.get(DEFAULT_WINDOW_REF))
        return as_of - timedelta(days=n - 1), as_of, f"last {n} days (default)", False

    def _values(self, kpi_id: str, start: date, end: date, accounts: list[str] | None,
                dims: list[str] | None) -> list[dict]:
        where, params = ["KPI_ID = ?", "PERIOD >= ?", "PERIOD <= ?", "VALUE IS NOT NULL"], [kpi_id, start, end]
        if accounts:
            where.append(f"ACCOUNT_NAME IN ({', '.join('?' for _ in accounts)})")
            params += accounts
        if dims:
            where.append(f"DIMENSION IN ({', '.join('?' for _ in dims)})")
            params += dims
        return self.db.query(f"SELECT ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM SEMANTIC.KPI_VALUES "
                             f"WHERE {' AND '.join(where)} ORDER BY PERIOD, ACCOUNT_NAME, DIMENSION", params)

    @staticmethod
    def _aggregate(rows: list[dict], aggregation: str) -> float | None:
        if not rows:
            return None
        vals = [float(r["VALUE"]) for r in rows]
        if aggregation == "sum":
            return sum(vals)
        if aggregation == "latest":
            last = max(r["PERIOD"] for r in rows)
            latest = [float(r["VALUE"]) for r in rows if r["PERIOD"] == last]
            return sum(latest) / len(latest) if len({r["DIMENSION"] for r in rows if r["PERIOD"] == last}) <= 1 \
                else sum(latest)
        if aggregation == "max":
            return max(vals)
        if aggregation == "min":
            return min(vals)
        return sum(vals) / len(vals)

    def _source_citations(self, d: dict, accounts: list[str], start: date, end: date) -> list[dict]:
        out = []
        for t in json.loads(d["SOURCES"] or "[]"):
            if t == "HARVEST_LOG":
                n = self.db.scalar("SELECT count(*) FROM RAW.HARVEST_LOG WHERE CAST(AS_OF AS DATE) BETWEEN ? AND ?",
                                   [start, end])
                out.append({"table": "RAW.HARVEST_LOG", "rows_in_window": int(n or 0), "basis": "AS_OF"})
            elif t in self._wm and self.db.relation_exists("RAW", t):
                col = self._wm[t]
                acc = f" AND ACCOUNT_NAME IN ({', '.join('?' for _ in accounts)})" if accounts else ""
                n = self.db.scalar(f'SELECT count(*) FROM RAW."{t}" WHERE CAST("{col}" AS DATE) BETWEEN ? AND ?{acc}',
                                   [start, end] + list(accounts or []))
                out.append({"table": f"RAW.{t}", "rows_in_window": int(n or 0), "basis": col})
            elif t in self._snap and self.db.relation_exists("CURATED", f"SNAP_{t}"):
                acc = f" AND ACCOUNT_NAME IN ({', '.join('?' for _ in accounts)})" if accounts else ""
                n = self.db.scalar(
                    f'SELECT count(*) FROM CURATED."SNAP_{t}" WHERE SNAPSHOT_DATE = '
                    f'(SELECT max(SNAPSHOT_DATE) FROM CURATED."SNAP_{t}" WHERE SNAPSHOT_DATE <= ?){acc}',
                    [end] + list(accounts or []))
                out.append({"table": f"RAW.{t}", "rows_in_window": int(n or 0), "basis": "snapshot <= window end"})
        return out

    # ------------------------------------------------------------------ main
    def ask(self, question: str, account: str | None = None) -> Answer:
        min_score = float(self.rubrics.get(MIN_SCORE_REF))
        candidates = self.match(question)
        if not candidates or candidates[0][0] < min_score:
            best = candidates[0] if candidates else (0.0, 0, None)
            return self._refuse(question, f"no certified KPI matches the question (best match "
                                          f"{best[2] or 'none'} at {best[0]:.2f} < {min_score:.2f})", best[0])
        score, _, kid = candidates[0]
        d = self._defs[kid]
        if not d["CERTIFIED"]:
            return self._refuse(question, f"{kid} ({d['NAME']}) is defined but not yet certified (status "
                                          f"{d['STATUS']}); no grounded value exists", score, kid)
        all_accounts = [r["ACCOUNT_NAME"] for r in self.db.query(
            "SELECT DISTINCT ACCOUNT_NAME FROM SEMANTIC.KPI_VALUES WHERE KPI_ID = ? ORDER BY 1", [kid])]
        accounts = [account] if account else [a for a in all_accounts if a.lower() in question.lower()]
        dims_all = [r["DIMENSION"] for r in self.db.query(
            "SELECT DISTINCT DIMENSION FROM SEMANTIC.KPI_VALUES WHERE KPI_ID = ? AND DIMENSION <> '' ORDER BY 1", [kid])]
        ql = question.lower()
        dims = [x for x in dims_all if x.lower() in ql]
        as_of = self._as_of(kid)
        if as_of is None:
            return self._refuse(question, f"{kid} has no computed values yet", score, kid)
        start, end, label, explicit = self.window(question, as_of, d["AGGREGATION"])
        rows = self._values(kid, start, end, accounts or None, dims or None)
        if not rows:
            return self._refuse(question, f"{kid} has no values for {label} ({start}..{end})", score, kid)
        agg = d["AGGREGATION"] or "avg"
        ranking = None
        is_ranking = bool(re.search(r"\b(which|top|most|highest|largest|biggest|lowest|least)\b", ql)) and not dims \
            and bool(dims_all)
        if is_ranking:
            by_dim: dict[str, list[dict]] = {}
            for r in rows:
                by_dim.setdefault(r["DIMENSION"], []).append(r)
            reverse = not re.search(r"\b(lowest|least)\b", ql)
            ranking = sorted(({"dimension": k, "value": self._aggregate(v, agg)} for k, v in by_dim.items()),
                             key=lambda x: (x["value"] is None, -(x["value"] or 0) if reverse else (x["value"] or 0)))
            value = ranking[0]["value"]
        else:
            value = self._aggregate(rows, agg)
        days = (end - start).days + 1
        periods = len({r["PERIOD"] for r in rows})
        coverage = 1.0 if agg == "latest" else min(1.0, periods / days)
        floor = float(self.rubrics.get(CONF_FLOOR_REF))
        confidence = round(min(1.0, (floor + (1 - floor) * score) * coverage), 3)
        unit = d["UNIT"]
        scope = ", ".join(accounts) if accounts else ", ".join(all_accounts)
        dim_txt = f" for {', '.join(dims)}" if dims else ""
        if ranking:
            top = "; ".join(f"{x['dimension']} {_fmt(x['value'], unit)}" for x in ranking[:3])
            text = (f"{d['NAME']} ({kid}), {label} [{start}..{end}], {scope}: highest is {ranking[0]['dimension']} "
                    f"at {_fmt(value, unit)}. Top: {top}.")
        else:
            how = {"sum": "total", "avg": "average", "latest": "latest", "max": "maximum", "min": "minimum"}.get(agg, agg)
            text = (f"{d['NAME']} ({kid}){dim_txt}, {label} [{start}..{end}], {scope}: {how} "
                    f"{_fmt(value, unit)}.")
        max_rows = int(self.rubrics.get(MAX_CITATIONS_REF))
        citations = [{
            "kpi_id": kid, "semantic_object": "SEMANTIC.KPI_VALUES", "kpi_table": d["KPI_TABLE"],
            "definition": d["DEFINITION"], "definition_hash": d["DEFINITION_HASH"], "rubric_version": d["RUBRIC_VERSION"],
            "rows": [{"account": r["ACCOUNT_NAME"], "period": r["PERIOD"].isoformat(), "dimension": r["DIMENSION"],
                      "value": float(r["VALUE"])} for r in rows[:max_rows]],
            "rows_total": len(rows),
            "source_tables": self._source_citations(d, accounts or all_accounts, start, end),
        }]
        rationale = (f"Matched the question to certified KPI {kid} '{d['NAME']}' (match score {score:.2f}); "
                     f"window {label} {'(explicit)' if explicit else '(defaulted)'}; "
                     f"{'dimension ' + ', '.join(dims) + '; ' if dims else ''}{len(rows)} KPI rows over "
                     f"{periods} period(s); aggregation {agg}; data coverage {coverage:.0%}.")
        ans = Answer(question, True, text, kid, value, unit, scope, ", ".join(dims) or None,
                     (start.isoformat(), end.isoformat()), ranking, citations, confidence, rationale)
        ans.inference_id = self._record(ans, "answer").inference_id
        return ans

    def _refuse(self, question: str, reason: str, score: float, kpi_id: str | None = None) -> Answer:
        text = ("I can't answer that from the certified platform KPIs: " + reason +
                ". Ask about a KPI in the catalogue (cost, performance, reliability, security, governance, usage, AI).")
        ans = Answer(question, False, text, kpi_id, confidence=round(float(score), 3),
                     rationale=f"Refused: {reason}.", refusal_reason=reason)
        ans.inference_id = self._record(ans, "refusal").inference_id
        return ans

    def _record(self, ans: Answer, kind: str) -> Inference:
        inf = Inference(
            kind=kind, subject_type="obs_question", subject_id=stable_id("Q", ans.question.strip().lower()),
            output=self.provider.complete("ask-the-platform", ans.text), confidence=float(ans.confidence),
            rationale=ans.rationale, model_id=self.provider.model_id, prompt_template=PROMPT_TEMPLATE,
            provider=self.provider.name,
            inputs_ref=f"SEMANTIC.KPI_VALUES:{ans.kpi_id}:{ans.window[0] if ans.window else ''}"
                       f"..{ans.window[1] if ans.window else ''}",
        )
        if self.store is not None:
            ReviewQueue(self.store, self.rubrics).record(inf, sample=False)
        return inf


def _fmt(v: float | None, unit: str | None) -> str:
    if v is None:
        return "n/a"
    if unit == "usd":
        return f"${v:,.2f}"
    if unit == "ratio":
        return f"{v * 100:.1f}%"
    if unit == "percent":
        return f"{v:+.1f}%"
    return f"{v:,.2f} {unit or ''}".strip()
