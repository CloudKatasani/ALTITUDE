"""Architecture Review Board (Section 17.3).

One decision is evaluated through seven lenses (``knowledge/advisory/review_board.yaml``).
Each lens states its key question, concerns and a vote (support / concerns / oppose).
The synthesis is a single recommendation with dissent recorded, stored as an ADR
in the ``decision`` table with evidence links. Humans decide; the board informs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from altitude.core import audit
from altitude.core.errors import ApprovalRequired
from altitude.core.expr import ExpressionError, evaluate
from altitude.core.ids import stable_id
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics

FACT_DEFAULTS: dict[str, Any] = {
    "annual_value_usd": None, "annual_cost_usd": None, "value_method_missing": False, "coexistence": False,
    "decommission_date": None, "requires_accountadmin": False, "row_data_leaves_boundary": False,
    "unmasked_classified_columns": 0, "wa_critical_findings": 0, "pattern": None, "modernise_backlog": False,
    "kpi_definition_conflicts": 0, "tier1_without_owner": 0, "estimate_p80_weeks": None, "deadline_weeks": None,
    "estimate_confidence": None, "in_quarter_end_blackout": False, "business_user_outcome": True,
    "emulates_legacy_physical_design": False,
}


@dataclass
class BoardResult:
    decision_id: str
    title: str
    recommendation: str
    support_share: float
    perspectives: list[dict]
    dissent: list[dict]
    evidence_refs: list[str]

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class ReviewBoard:
    def __init__(self, rubrics: RubricSet | None = None, store: Any = None):
        self.rubrics = rubrics or default_rubrics()
        self.store = store
        self.lenses = load_yaml("advisory/review_board.yaml")["lenses"]

    def review(self, title: str, facts: dict, evidence_refs: list[str] | None = None,
               engagement_id: str | None = None, context: str = "") -> BoardResult:
        ctx = {**FACT_DEFAULTS, **facts}
        perspectives = []
        total_w = support_w = 0.0
        for lens in self.lenses:
            concerns, blocking = [], False
            for c in lens["concerns"]:
                try:
                    hit = evaluate(c["when"], ctx, self.rubrics)
                except ExpressionError as e:
                    concerns.append({"concern": f"cannot evaluate ({e}); supply the missing fact", "blocking": False})
                    continue
                if hit:
                    concerns.append({"concern": c["concern"], "blocking": c["blocking"]})
                    blocking = blocking or c["blocking"]
            vote = "oppose" if blocking else ("concerns" if concerns else "support")
            w = float(lens["weight"])
            total_w += w
            support_w += w if vote == "support" else (w / 2 if vote == "concerns" else 0.0)
            perspectives.append({"lens": lens["id"], "name": lens["name"], "key_question": lens["key_question"],
                                 "vote": vote, "concerns": concerns})
        share = round(support_w / total_w, 4) if total_w else 0.0
        floor = float(self.rubrics.get("rubric.advisory.review_board.proceed_support_min"))
        if any(p["vote"] == "oppose" for p in perspectives):
            rec = "do_not_proceed_until_blockers_resolved"
        elif share >= floor:
            rec = "proceed"
        else:
            rec = "proceed_with_conditions"
        majority = "support" if rec == "proceed" else "oppose"
        dissent = [p for p in perspectives if (p["vote"] == "oppose") != (majority == "oppose") and p["vote"] != "concerns"]
        did = stable_id("ADR", title, sorted(facts.items(), key=lambda kv: kv[0]).__repr__())
        result = BoardResult(did, title, rec, share, perspectives, dissent, list(evidence_refs or []))
        if self.store is not None and engagement_id:
            if not self.store.get("decision", decision_id=did):
                self.store.insert("decision", {
                    "decision_id": did, "engagement_id": engagement_id, "title": title, "context": context,
                    "recommendation": rec, "perspectives": {"lenses": perspectives, "support_share": share},
                    "dissent": {"lenses": dissent}, "evidence_refs": list(evidence_refs or []), "status": "proposed",
                })
        return result

    def decide(self, decision_id: str, decided_by: str, accept: bool) -> None:
        """Record the human decision on a board recommendation (the board never decides itself)."""
        if not decided_by:
            raise ApprovalRequired("a named decision maker is required")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        self.store.update("decision", {"decision_id": decision_id},
                          {"status": "accepted" if accept else "rejected", "decided_by": decided_by, "decided_at": now})
        audit.record(self.store, decided_by, "decision.accept" if accept else "decision.reject",
                     subject_type="decision", subject_id=decision_id)
