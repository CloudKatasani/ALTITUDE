"""Package O — Platform Observability (Section 7).

Pipeline::

    sources (synthetic | live Snowflake, read-only)
      → harvest   (config-driven, multi-account; knowledge/observability/sources.yaml)
      → RAW       immutable, append-only archive de-duplicated by row hash
      → CURATED   conformed facts and dimensions (knowledge/observability/curated.yaml)
      → KPI       KPI tables computed from the catalogue (knowledge/observability/kpis/*.yaml)
      → SEMANTIC  certified KPI definitions + long-format values
      → dashboards · alerts (routes/runbooks as data) · ask-the-platform agent · suggestion-to-value loop

Every threshold is a ``rubric.obs.*`` reference (``knowledge/rubrics/obs.yaml``).
"""

from .db import ObsDatabase  # noqa: F401
