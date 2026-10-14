"""AI mismatch triage: cluster mismatches by root-cause signature and link them to the Pattern Library.

Signatures are derived in-boundary from mismatched rows (values never leave the boundary);
only the cluster (signature, column, count, known issue, fix, confidence, rationale) is stored.
Every cluster is recorded as an :class:`~altitude.core.ai.Inference` through the
:class:`~altitude.core.ai.ReviewQueue`, so low-confidence clusters wait for human review.
The default provider is the deterministic offline template (no LLM call); its rationale is
assembled from the evidence counts and the Pattern Library entry.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterable

from altitude.core.ai import Inference, ReviewQueue, TemplateProvider
from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet

from .config import ValidationKnowledge

PROMPT_TEMPLATE = "validation.mismatch_triage@1.0.0"
WILDCARD = "*"


def classify(s: Any, t: Any, rubrics: RubricSet) -> str:
    """Root-cause signature for one differing column value pair (source ``s``, target ``t``)."""
    if s is None or t is None:
        other = t if s is None else s
        if isinstance(other, str) and other == "":
            return "empty_vs_null"
        return "unexplained"
    if isinstance(s, str) and isinstance(t, str):
        if s.rstrip(" ") == t.rstrip(" "):
            return "trailing_space"
        if s.upper() == t.upper() or s.rstrip(" ").upper() == t.rstrip(" ").upper():
            return "case_only"
        return "unexplained"
    if isinstance(s, (date, datetime)) and isinstance(t, (date, datetime)):
        sd = s if isinstance(s, datetime) else datetime.combine(s, time())
        td = t if isinstance(t, datetime) else datetime.combine(t, time())
        if sd.date() == td.date() and td.time() == time() and sd.time() != time():
            return "time_component_lost"
        diff = abs(sd - td)
        limit = timedelta(milliseconds=float(rubrics.get("rubric.validation.triage.timestamp_precision_max_ms")))
        if diff < limit:
            return "timestamp_precision"
        if diff.total_seconds() % 3600 == 0:  # whole hours
            return "timezone_shift"
        return "unexplained"
    if isinstance(s, (int, float, Decimal)) and isinstance(t, (int, float, Decimal)) \
            and not isinstance(s, bool) and not isinstance(t, bool):
        if isinstance(s, float) or isinstance(t, float):
            tol = float(rubrics.get("rubric.validation.triage.float_rel_tolerance"))
            if math.isclose(float(s), float(t), rel_tol=tol):
                return "float_precision"
            return "unexplained"
        ds, dt = Decimal(s), Decimal(t)
        t_places = max(0, -dt.normalize().as_tuple().exponent)
        s_places = max(0, -ds.normalize().as_tuple().exponent)
        if t_places < s_places:
            q = Decimal(1).scaleb(-t_places)
            if dt in (ds.quantize(q, rounding="ROUND_HALF_UP"), ds.quantize(q, rounding="ROUND_DOWN"),
                      ds.quantize(q, rounding="ROUND_HALF_EVEN")):
                return "scale_truncation"
        return "unexplained"
    return "unexplained"


@dataclass
class Cluster:
    level: str
    signature: str
    column: str
    count: int
    total: int
    known_issue_id: str | None
    fix_pattern_id: str | None
    confidence: float
    rationale: str
    cluster_id: str = ""

    @property
    def signature_key(self) -> str:
        return f"{self.signature}:{self.column}"


@dataclass
class Triage:
    knowledge: ValidationKnowledge
    rubrics: RubricSet
    source_dialect: str
    object_id: str
    library: Any = None           # PatternLibrary (lazy)
    observations: Counter = field(default_factory=Counter)   # (level, signature, column) -> rows

    def observe(self, level: str, signature: str, column: str, n: int = 1) -> None:
        self.observations[(level, signature, column)] += n

    def _lib(self):
        if self.library is None:
            from altitude.patterns.library import default_library

            self.library = default_library()
        return self.library

    def clusters(self, run_ids: dict[str, str], totals: dict[str, int]) -> list[Cluster]:
        out: list[Cluster] = []
        for (level, sig, col), n in sorted(self.observations.items()):
            sig_def = self.knowledge.signatures.get(sig) or self.knowledge.signatures["unexplained"]
            issue_id = sig_def.issue_by_dialect.get(self.source_dialect)
            conf = float(self.rubrics.get(sig_def.confidence_ref))
            if n < int(self.rubrics.get("rubric.validation.triage.min_cluster_size")):
                conf *= float(self.rubrics.get("rubric.validation.triage.small_cluster_factor"))
            if issue_id is None and sig_def.issue_by_dialect:
                conf *= float(self.rubrics.get("rubric.validation.triage.unmapped_dialect_factor"))
            conf = round(conf, 3)
            total = totals.get(level, n)
            fix_id, rationale = None, ""
            where = "rows" if col == WILDCARD else f"rows differ in column {col}"
            evidence = f"{n} of {total} mismatched {where}" if col != WILDCARD else f"{n} of {total} mismatched rows"
            if issue_id:
                issue = self._lib().issues.get(issue_id)
                if issue is not None:
                    fix = issue.primary_fix
                    fix_id = fix.id
                    rationale = (f"{evidence} with signature '{sig}' ({sig_def.description.lower()}). For "
                                 f"{self.source_dialect} sources this is {issue.id} '{issue.title}' "
                                 f"[{issue.severity}]. Suggested fix {fix.id}: {fix.description}.")
            if not rationale:
                rationale = (f"{evidence} with signature '{sig}' ({sig_def.description.lower()}); no Pattern Library "
                             f"issue is mapped for {self.source_dialect} sources, so a human must triage.")
            c = Cluster(level, sig, col, n, total, issue_id, fix_id, conf, rationale)
            c.cluster_id = stable_id("MMC", run_ids.get(level, ""), level, sig, col)
            out.append(c)
        return out


def record_clusters(store, clusters: Iterable[Cluster], run_ids: dict[str, str], mismatch_refs: dict[str, str],
                    rubrics: RubricSet, tenant_id: str | None = None) -> list[str]:
    """Persist clusters and their AI inferences; returns review item subjects enqueued."""
    queue = ReviewQueue(store, rubrics)
    provider = TemplateProvider()
    for c in clusters:
        run_id = run_ids[c.level]
        if not store.get("mismatch_cluster", cluster_id=c.cluster_id):
            store.insert("mismatch_cluster", {
                "cluster_id": c.cluster_id, "run_id": run_id, "signature": c.signature_key,
                "known_issue_id": c.known_issue_id, "mismatch_count": c.count,
                "confidence": c.confidence, "rationale": c.rationale,
            })
        output = json.dumps({"signature": c.signature, "column": c.column, "known_issue_id": c.known_issue_id,
                             "fix_pattern_id": c.fix_pattern_id}, sort_keys=True)
        queue.record(Inference(
            kind="classification", subject_type="mismatch_cluster", subject_id=c.cluster_id,
            output=provider.complete(PROMPT_TEMPLATE, output), confidence=c.confidence, rationale=c.rationale,
            model_id=provider.model_id, prompt_template=PROMPT_TEMPLATE, provider=provider.name,
            inputs_ref=mismatch_refs.get(c.level), tenant_id=tenant_id,
        ))
    return [c.cluster_id for c in clusters]
