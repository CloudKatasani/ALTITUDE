"""M6 Validation engine: tiered L0-L5 reconciliation, normalisation as data, AI mismatch triage,
accepted-deviation workflow and tier summaries for the go/no-go pack (Section 12.3).

Typical use (in-boundary)::

    from altitude.validation import Endpoint, TableSpec, ValidationEngine, generate_suite
    suite = generate_suite(TableSpec(object_id="SALES.ORDERS", source_table="orders", tier="tier1",
                                     key_columns=["order_id"], source_dialect="teradata"))
    result = ValidationEngine(store, Endpoint(src_con), Endpoint(tgt_con, "snowflake"), "./mismatch").run(suite)
"""

from .deviation import accept_deviation, assign_data_owner, deviations
from .endpoint import Endpoint
from .engine import LevelResult, RunResult, ValidationEngine
from .normalise import Normaliser
from .suite import PerfSpec, QuerySpec, Suite, TableSpec, generate_suite, persist_suite
from .summary import render_md, tier_summary

__all__ = [
    "Endpoint", "LevelResult", "Normaliser", "PerfSpec", "QuerySpec", "RunResult", "Suite", "TableSpec",
    "ValidationEngine", "accept_deviation", "assign_data_owner", "deviations", "generate_suite", "persist_suite",
    "render_md", "tier_summary",
]
