"""Evidence retrieval for grounded answers (deterministic BM25 over evidence documents)."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Iterable

from altitude.core.rubric import RubricSet, default_rubrics

_TOKEN = re.compile(r"[a-z0-9_]+")
_STOP = {
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "by", "with", "what", "which",
    "who", "how", "why", "our", "we", "my", "do", "does", "it", "this", "that", "from", "at", "as", "can", "should",
    "there", "any", "me", "show", "tell", "about", "where", "i", "you",
}


def tokens(text: str) -> list[str]:
    out = []
    for t in _TOKEN.findall(text.lower()):
        if t in _STOP:
            continue
        out.append(t)
        if "_" in t:
            out.extend(p for p in t.split("_") if p and p not in _STOP)
    return out


@dataclass(frozen=True)
class GroundingDoc:
    """A citable unit of evidence: a suggestion, evidence record, known issue, KPI value, gate result..."""

    id: str
    kind: str
    title: str
    text: str
    tags: tuple[str, ...] = ()
    data: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)

    def body(self) -> str:
        return f"{self.id} {self.title} {self.text} {' '.join(self.tags)}"


@dataclass
class Hit:
    doc: GroundingDoc
    score: float


class GroundingIndex:
    def __init__(self, rubrics: RubricSet | None = None):
        self.rubrics = rubrics or default_rubrics()
        self.docs: dict[str, GroundingDoc] = {}
        self._tf: dict[str, Counter] = {}
        self._df: Counter = Counter()

    def add(self, docs: Iterable[GroundingDoc]) -> "GroundingIndex":
        for d in docs:
            if d.id in self.docs:
                for t in self._tf[d.id]:
                    self._df[t] -= 1
            self.docs[d.id] = d
            tf = Counter(tokens(d.body()))
            self._tf[d.id] = tf
            for t in tf:
                self._df[t] += 1
        return self

    def __len__(self) -> int:
        return len(self.docs)

    def get(self, doc_id: str) -> GroundingDoc | None:
        return self.docs.get(doc_id)

    def search(self, query: str, k: int | None = None, kinds: Iterable[str] | None = None,
               tags: Iterable[str] | None = None) -> list[Hit]:
        k1 = float(self.rubrics.get("rubric.advisory.grounding.k1"))
        b = float(self.rubrics.get("rubric.advisory.grounding.b"))
        kinds = set(kinds or [])
        tagset = set(tags or [])
        q = tokens(query)
        # exact ID mentions are always strong evidence
        ids = {m.upper() for m in re.findall(r"[A-Za-z]{2,5}-[A-Za-z]*-?\d+[A-Za-z0-9-]*", query)}
        n = len(self.docs) or 1
        avgdl = (sum(sum(tf.values()) for tf in self._tf.values()) / n) if self.docs else 1.0
        hits = []
        for doc_id, tf in self._tf.items():
            doc = self.docs[doc_id]
            if kinds and doc.kind not in kinds:
                continue
            if tagset and not (tagset & set(doc.tags)):
                continue
            dl = sum(tf.values()) or 1
            score = 0.0
            for t in set(q):
                if t not in tf:
                    continue
                idf = math.log(1 + (n - self._df[t] + 0.5) / (self._df[t] + 0.5))
                score += idf * tf[t] * (k1 + 1) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
            if doc_id.upper() in ids:
                score += float(self.rubrics.get("rubric.advisory.grounding.confidence_scale"))
            if score > 0:
                hits.append(Hit(doc, round(score, 6)))
        hits.sort(key=lambda h: (-h.score, h.doc.id))
        return hits[: k or int(self.rubrics.get("rubric.advisory.grounding.max_citations"))]


# --------------------------------------------------------------------------- document adapters


def docs_from_suggestions(suggestions: Iterable[dict]) -> list[GroundingDoc]:
    out = []
    for s in suggestions:
        value = (s.get("value") or {}).get("annualised_usd") or {}
        text = (
            f"{s.get('title', '')}. Check {s.get('check_id')} in domain {s.get('domain')} ({s.get('waf_pillar')}). "
            f"Affected: {', '.join(s.get('affected_objects') or [])}. "
            f"Value p50 ${value.get('p50', 0):,.0f} (conservative ${value.get('conservative', 0):,.0f}); "
            f"method: {(s.get('value') or {}).get('method', 'n/a')}. Rationale: {s.get('rationale', '')}. "
            f"Priority {((s.get('priority') or {}).get('quadrant'))}. Status {s.get('status')}. "
            f"Evidence: {', '.join(s.get('evidence_refs') or [])}."
        )
        tags = tuple(t for t in (s.get("domain"), s.get("waf_pillar"), _pillar_tag(s.get("waf_pillar"))) if t)
        out.append(GroundingDoc(s["id"], "suggestion", s.get("title", s["id"]), text, tags, dict(s)))
    return out


def _pillar_tag(pillar: str | None) -> str | None:
    return {
        "cost_optimization": "cost", "performance_efficiency": "performance", "reliability": "reliability",
        "security_governance": "security", "operational_excellence": "operations",
    }.get(pillar or "")


def docs_from_known_issues(issues: Iterable[dict]) -> list[GroundingDoc]:
    out = []
    for i in issues:
        fixes = "; ".join(f.get("description", "") for f in i.get("fix_patterns", []) if isinstance(f, dict))
        text = f"{i.get('title', '')}. Severity {i.get('severity')}. Fix: {fixes or i.get('fix', '')}"
        dialect = i.get("source_dialect") or i.get("dialect") or ""
        out.append(GroundingDoc(i["id"], "known_issue", i.get("title", i["id"]), text, (dialect,), dict(i)))
    return out


def docs_from_records(records: Iterable[dict], kind: str, id_key: str = "id", title_key: str = "title",
                      tags: tuple[str, ...] = ()) -> list[GroundingDoc]:
    out = []
    for r in records:
        text = "; ".join(f"{k}={v}" for k, v in sorted(r.items()) if not k.startswith("_") and v not in (None, "", []))
        out.append(GroundingDoc(str(r[id_key]), kind, str(r.get(title_key, r[id_key])), text, tags, dict(r)))
    return out


def load_known_issue_docs() -> list[GroundingDoc]:
    """Known issues from the Pattern Library (``knowledge/dialects/*/known_issues.yaml``), if present."""
    from altitude.core.knowledge import load_entries

    issues = []
    for key in ("known_issues", "issues"):
        issues = load_entries("dialects/*/known_issues.yaml", key)
        if issues:
            break
    for i in issues:
        i.setdefault("source_dialect", i.get("_source", "").split("/")[1] if "/" in i.get("_source", "") else "")
    return docs_from_known_issues(issues)


def format_metrics(metrics: Any) -> str:
    """Readable ``Label value`` pairs for evidence metrics (shares as %, counts with separators)."""
    import json

    if isinstance(metrics, str):
        try:
            metrics = json.loads(metrics)
        except ValueError:
            return metrics
    if not isinstance(metrics, dict):
        return str(metrics)
    parts = []
    for key, v in metrics.items():
        if v is None or v == "":
            continue
        label = key.replace("_", " ").lower()
        label = label[0].upper() + label[1:]
        if isinstance(v, bool):
            text = "yes" if v else "no"
        elif isinstance(v, (int, float)) and any(t in key.upper() for t in ("SHARE", "PCT", "RATIO", "RATE")):
            text = f"{float(v):.0%}"
        elif isinstance(v, int):
            text = f"{v:,}"
        elif isinstance(v, float):
            text = f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}"  # threshold-ok: display precision
        else:
            text = str(v).replace(",", ", ") if isinstance(v, str) and "," in v and " " not in v else str(v)
        parts.append(f"{label} {text}")
    return "; ".join(parts)
