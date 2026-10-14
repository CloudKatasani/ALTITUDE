"""Sherpa — the opinionated, grounded AI delivery partner (Section 17.1).

- Answers only from the grounding index (engagement snapshot + Pattern Library)
  and cites evidence IDs; refuses when the best evidence is below the rubric
  grounding floor.
- Challenges risky plans unprompted (rules in ``knowledge/advisory/sherpa.yaml``).
- Proposes the next three actions for the current phase.
- Every answer is recorded as an ``Inference`` (confidence + rationale).
"""

from __future__ import annotations

import string
from dataclasses import dataclass, field
from typing import Any, Iterable

from altitude.core.ai import Inference, ReviewQueue, TemplateProvider
from altitude.core.expr import ExpressionError, evaluate
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.theme import token

from .grounding import GroundingIndex, Hit

PROMPT_TEMPLATE = "sherpa.answer@1.0.0"


class _Fmt(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _format(template: str, facts: dict) -> str:
    return string.Formatter().vformat(template, (), _Fmt(facts))


@dataclass
class Answer:
    question: str
    text: str
    grounded: bool
    citations: list[str]
    confidence: float
    rationale: str
    challenges: list[dict] = field(default_factory=list)
    inference_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question, "answer": self.text, "grounded": self.grounded, "citations": self.citations,
            "confidence": self.confidence, "rationale": self.rationale, "challenges": self.challenges,
            "inference_id": self.inference_id,
        }


class Sherpa:
    def __init__(self, index: GroundingIndex, rubrics: RubricSet | None = None, store: Any = None,
                 advisor: dict | None = None, provider: Any = None):
        self.index = index
        self.rubrics = rubrics or default_rubrics()
        self.store = store
        self.advisor = advisor
        self.provider = provider or TemplateProvider()
        self.rules = load_yaml("advisory/sherpa.yaml")

    # ------------------------------------------------------------------ advisors
    @classmethod
    def advisor(cls, advisor_id: str, index: GroundingIndex, **kw: Any) -> "Sherpa":
        advisors = {a["id"]: a for a in load_yaml("advisory/advisors.yaml")["advisors"]}
        if advisor_id not in advisors:
            raise KeyError(f"unknown advisor {advisor_id}")
        return cls(index, advisor=advisors[advisor_id], **kw)

    @property
    def name(self) -> str:
        return self.advisor["name"] if self.advisor else token("COPILOT_NAME")

    # ------------------------------------------------------------------ answering
    def _search(self, question: str) -> list[Hit]:
        if self.advisor:
            hits = self.index.search(question, kinds=self.advisor["kinds"], tags=self.advisor["tags"])
            return hits or self.index.search(question, kinds=self.advisor["kinds"])
        return self.index.search(question)

    def ask(self, question: str, facts: dict | None = None) -> Answer:
        hits = self._search(question)
        floor = float(self.rubrics.get("rubric.advisory.grounding.min_score"))
        scale = float(self.rubrics.get("rubric.advisory.grounding.confidence_scale"))
        challenges = self.challenges(facts or {})
        if not hits or hits[0].score < floor:
            text = (f"I can't answer that from the engagement evidence. Nothing in the snapshot or the Pattern Library "
                    f"supports an answer, so I won't guess. Try naming an object, check, KPI or issue ID.")
            ans = Answer(question, text, False, [], 0.0,
                         f"best evidence score {hits[0].score if hits else 0:.2f} below grounding floor", challenges)
            return self._record(ans)
        top = [h for h in hits if h.score >= floor]
        lines = [f"{self.name}: based on {len(top)} evidence item(s):"]
        for h in top:
            lines.append(f"- [{h.doc.id}] {h.doc.title}: {self._summary(h)}")
        for c in challenges:
            lines.append(f"! [{c['id']}] {c['message']}")
        text = self.provider.complete("Answer strictly from the cited evidence.", "\n".join(lines))
        confidence = round(min(1.0, top[0].score / scale), 3)
        rationale = (f"retrieved {len(top)} evidence item(s) above the grounding floor; best match {top[0].doc.id} "
                     f"(score {top[0].score:.2f})")
        return self._record(Answer(question, text, True, [h.doc.id for h in top], confidence, rationale, challenges))

    @staticmethod
    def _summary(hit: Hit) -> str:
        text = hit.doc.text
        return text if len(text) <= 400 else text[:397] + "..."  # threshold-ok: display truncation length

    def _record(self, ans: Answer) -> Answer:
        if self.store is None:
            return ans
        inf = Inference(kind="answer", subject_type="question", subject_id=ans.question[:120], output=ans.text,
                        confidence=ans.confidence, rationale=ans.rationale, model_id=self.provider.model_id,
                        prompt_template=PROMPT_TEMPLATE, provider=self.provider.name,
                        inputs_ref=",".join(ans.citations) or None)
        ReviewQueue(self.store, self.rubrics).record(inf, sample=False)
        ans.inference_id = inf.inference_id
        return ans

    # ------------------------------------------------------------------ opinions
    def challenges(self, facts: dict) -> list[dict]:
        out = []
        ctx = _with_defaults(facts)
        for rule in self.rules["challenges"]:
            try:
                fired = evaluate(rule["when"], ctx, self.rubrics)
            except ExpressionError:
                continue  # rule needs facts this engagement hasn't supplied
            if fired:
                out.append({"id": rule["id"], "title": rule["title"], "severity": rule["severity"],
                            "message": _format(rule["message"], ctx)})
        return out

    def next_actions(self, phase: str, facts: dict, n: int = 3) -> list[str]:
        ctx = _with_defaults(facts)
        actions = []
        for item in self.rules["next_actions"].get(phase, []):
            try:
                ok = evaluate(item["when"], ctx, self.rubrics)
            except ExpressionError:
                ok = False
            if ok:
                actions.append(_format(item["action"], ctx))
            if len(actions) == n:
                break
        return actions


def _with_defaults(facts: dict) -> dict:
    ctx = dict(facts)
    if "dead_object_share" in ctx and "dead_object_share_pct" not in ctx:
        ctx["dead_object_share_pct"] = round(float(ctx["dead_object_share"]) * 100)
    return ctx


def build_index(suggestions: Iterable[dict] = (), extra: Iterable = (), include_pattern_library: bool = True,
                rubrics: RubricSet | None = None) -> GroundingIndex:
    from .grounding import docs_from_suggestions, load_known_issue_docs

    idx = GroundingIndex(rubrics)
    idx.add(docs_from_suggestions(suggestions))
    if include_pattern_library:
        idx.add(load_known_issue_docs())
    idx.add(extra)
    return idx
