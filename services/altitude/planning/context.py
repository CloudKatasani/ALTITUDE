"""Planning inputs: a sealed assessment snapshot, the harvest snapshot it was computed from, and the
programme inputs from the Appendix B questionnaire (deadline, appetite for change, ...)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

from altitude.assessment.engine import AssessmentResult, load_assessment
from altitude.assessment.estate import Estate
from altitude.core.errors import AltitudeError
from altitude.core.snapshot import Snapshot

PROCEDURAL_TYPES = frozenset({"procedure", "function", "package", "trigger", "macro", "script"})
TAG_KINDS = frozenset({"schedules", "writes"})  # what a tagged process runs and populates


@dataclass
class PlanObject:
    object_id: str
    fq_name: str
    object_type: str
    loc: int
    usage_90d: int
    disposition: str
    needs_review: bool
    band: str
    score: float
    constructs: set[str] = field(default_factory=set)
    s1_issues: int = 0
    attrs: dict[str, str] = field(default_factory=dict)


class PlanningContext:
    def __init__(self, assessment: AssessmentResult, harvest: Snapshot, inputs: dict[str, Any] | None = None):
        if assessment.harvest_snapshot_id != harvest.snapshot_id:
            raise AltitudeError(f"assessment {assessment.snapshot_id} was computed from {assessment.harvest_snapshot_id}, "
                                f"not {harvest.snapshot_id}")
        self.assessment = assessment
        self.harvest = harvest
        self.estate = Estate(harvest)
        self.inputs = dict(inputs or {})
        disp = {r["object_id"]: r for r in assessment.rows("object_disposition")}
        cx = {r["object_id"]: r for r in assessment.rows("complexity_score")}
        s1: dict[str, int] = {}
        for h in assessment.rows("drift_hit"):
            if h["severity"] == "S1":
                s1[h["object_id"]] = s1.get(h["object_id"], 0) + 1
        self.objects: dict[str, PlanObject] = {}
        for oid, o in sorted(self.estate.objects.items()):
            d, c = disp[oid], cx[oid]
            self.objects[oid] = PlanObject(oid, o.fq_name, o.object_type, o.loc, o.usage_90d, d["disposition"],
                                           bool(d["needs_review"]), c["band"], float(c["score"]),
                                           set(c["factors"]) - {"loc_per_100", "dependency_fan_out"},
                                           s1.get(oid, 0), dict(o.attrs))

    # ------------------------------------------------------------------ loading
    @classmethod
    def load(cls, assessment: str | Path | AssessmentResult, harvest: str | Path | Snapshot | None = None,
             store: Any = None, inputs: dict[str, Any] | None = None) -> "PlanningContext":
        result = assessment if isinstance(assessment, AssessmentResult) else load_assessment(assessment)
        if harvest is None:
            if store is None:
                raise AltitudeError("the harvest snapshot path (or a store that registered it) is required")
            row = store.get("snapshot", snapshot_id=result.harvest_snapshot_id)
            if row is None:
                raise AltitudeError(f"harvest snapshot {result.harvest_snapshot_id} is not registered in the store")
            harvest = row["location"]
        snap = harvest if isinstance(harvest, Snapshot) else Snapshot.open(harvest, verify=True)
        return cls(result, snap, inputs)

    # ------------------------------------------------------------------ views
    @property
    def snapshot_id(self) -> str:
        return self.assessment.snapshot_id

    @property
    def engagement_id(self) -> str | None:
        return self.assessment.summary.get("engagement_id")

    @property
    def as_of(self) -> date:
        return self.estate.as_of.date()

    def in_scope(self) -> list[str]:
        return [oid for oid, o in self.objects.items() if o.disposition != "retire"]

    def retired(self) -> list[str]:
        return [oid for oid, o in self.objects.items() if o.disposition == "retire"]

    def name(self, oid: str) -> str:
        return self.objects[oid].fq_name

    def start_date(self) -> date:
        v = self.inputs.get("start_date")
        if v:
            return date.fromisoformat(str(v))
        d = self.as_of + timedelta(days=1)
        return d + timedelta(days=(7 - d.weekday()) % 7)  # next Monday

    def tags(self) -> dict[str, set[str]]:
        """Freeze tags. ``month_end`` comes from monthly schedules, ``regulatory`` from the questionnaire's object
        patterns; both propagate to what a tagged process schedules and writes, and to the views/reports that read
        a tagged table (the regulatory report itself). Shared helpers merely *called* are not tagged."""
        seeds: dict[str, set[str]] = {}
        for oid, o in self.objects.items():
            freq = o.attrs.get("schedule_frequency", "")
            if "monthly" in freq or o.attrs.get("month_end") == "True":
                seeds.setdefault(oid, set()).add("month_end")
            for pat in self.inputs.get("regulatory_objects", []):
                if fnmatch.fnmatch(o.fq_name.lower(), str(pat).lower()):
                    seeds.setdefault(oid, set()).add("regulatory")
        tags = {k: set(v) for k, v in seeds.items()}
        for oid, t in seeds.items():
            stack, seen = [oid], {oid}
            while stack:
                cur = stack.pop()
                for tgt, kind in self.estate.outbound.get(cur, []):
                    if kind in TAG_KINDS and tgt not in seen:
                        seen.add(tgt)
                        tags.setdefault(tgt, set()).update(t)
                        stack.append(tgt)
                if self.objects[cur].object_type == "table":
                    for reader, kind in self.estate.inbound.get(cur, []):
                        if kind == "reads" and self.objects[reader].object_type in {"view", "report"}:
                            tags.setdefault(reader, set()).update(t)
        return tags

    def edges_within(self, ids: Iterable[str], kinds: Iterable[str]) -> list[tuple[str, str, str]]:
        ids, kinds = set(ids), set(kinds)
        return [(f, t, k) for f, t, k in self.estate.edges if f in ids and t in ids and k in kinds]
