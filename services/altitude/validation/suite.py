"""L0-L5 suite generator: which checks run for a table, by tier (Section 12.3 levels as data)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from altitude.core.ids import stable_id
from altitude.core.rubric import RubricSet, default_rubrics

from .config import LEVELS, ValidationKnowledge, default_knowledge
from .normalise import Normaliser


@dataclass
class QuerySpec:
    """L4 business-output check: the same KPI/report query on both sides (dialect-specific text allowed)."""

    id: str
    source_sql: str
    target_sql: str | None = None
    description: str = ""


@dataclass
class PerfSpec:
    """L5 timings supplied by the caller (query history / benchmark harness), in milliseconds."""

    query_id: str
    baseline_p50_ms: float
    baseline_p95_ms: float
    target_p50_ms: float
    target_p95_ms: float
    sla_p95_ms: float | None = None


@dataclass
class TableSpec:
    object_id: str
    source_table: str
    target_table: str | None = None
    tier: str = "tier1"
    key_columns: list[str] = field(default_factory=list)
    partition_column: str | None = None
    columns: list[str] | None = None
    policies: list[str] = field(default_factory=list)
    source_dialect: str = "teradata"
    engagement_id: str = "ENG-LOCAL"
    data_owner: str | None = None
    queries: list[QuerySpec] = field(default_factory=list)
    perf: list[PerfSpec] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.target_table = self.target_table or self.source_table
        self.queries = [q if isinstance(q, QuerySpec) else QuerySpec(**q) for q in self.queries]
        self.perf = [p if isinstance(p, PerfSpec) else PerfSpec(**p) for p in self.perf]

    @classmethod
    def from_dict(cls, d: dict) -> "TableSpec":
        return cls(**d)


@dataclass
class Check:
    check_id: str
    level: str
    mode: str
    definition: dict


@dataclass
class Suite:
    suite_id: str
    spec: TableSpec
    tier: str
    levels: dict[str, str]
    checks: list[Check]
    threshold_ref: str
    normaliser: Normaliser

    def checks_for(self, level: str) -> list[Check]:
        return [c for c in self.checks if c.level == level]

    @property
    def active_levels(self) -> list[str]:
        return [lv for lv in LEVELS if self.checks_for(lv)]


def generate_suite(spec: TableSpec, knowledge: ValidationKnowledge | None = None,
                   rubrics: RubricSet | None = None) -> Suite:
    knowledge = knowledge or default_knowledge()
    rubrics = rubrics or default_rubrics()
    tier = knowledge.tier(spec.tier)
    levels = dict(tier["levels"])
    normaliser = Normaliser(tuple(spec.policies), knowledge)
    ident = ["VS", spec.object_id, spec.tier, levels, spec.key_columns, spec.partition_column, spec.columns,
             normaliser.version, [q.id for q in spec.queries], [p.query_id for p in spec.perf]]
    suite_id = stable_id("VS", *ident)
    checks: list[Check] = []

    def add(level: str, definition: dict) -> None:
        mode = levels[level]
        if mode == "none":
            return
        checks.append(Check(stable_id("VC", suite_id, level, definition), level, mode, dict(definition, mode=mode)))

    add("L0", {"kind": "schema_parity"})
    add("L1", {"kind": "row_count", "partition_column": spec.partition_column})
    l2: dict[str, Any] = {"kind": "column_aggregates", "columns": spec.columns or "all"}
    if levels["L2"] == "sample":
        l2["sample_partitions_ref"] = "rubric.validation.sampling.l2_sample_partitions"
    add("L2", l2)
    if spec.key_columns:
        l3: dict[str, Any] = {"kind": "row_hash", "key_columns": spec.key_columns, "columns": spec.columns or "all"}
        if levels["L3"] == "sample":
            l3["sample_rate_ref"] = "rubric.validation.sampling.l3_sample_rate"
        add("L3", l3)
    for q in spec.queries:
        add("L4", {"kind": "query_diff", "query_id": q.id})
    if spec.perf:
        add("L5", {"kind": "performance", "query_ids": [p.query_id for p in spec.perf]})
    return Suite(suite_id, spec, spec.tier, levels, checks, tier["threshold_ref"], normaliser)


def persist_suite(store, suite: Suite, now: datetime | None = None) -> None:
    if store.get("validation_suite", suite_id=suite.suite_id):
        return
    store.insert("validation_suite", {
        "suite_id": suite.suite_id,
        "engagement_id": suite.spec.engagement_id,
        "object_id": suite.spec.object_id,
        "tier": suite.tier,
        "levels": suite.active_levels,
        "generated_at": (now or datetime.now(timezone.utc)).replace(tzinfo=None),
    })
    store.insert("validation_check", [{
        "check_id": c.check_id, "suite_id": suite.suite_id, "level": c.level,
        "definition": dict(c.definition, spec=_spec_ref(suite.spec)),
    } for c in suite.checks])


def _spec_ref(spec: TableSpec) -> dict:
    d = asdict(spec)
    d["queries"] = [q["id"] for q in d["queries"]]
    return {k: d[k] for k in ("object_id", "source_table", "target_table", "key_columns", "partition_column",
                              "policies", "source_dialect", "queries")}
