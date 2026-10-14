-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-04: Daily full reloads of large tables
-- Domain D1 · WAF pillar cost_optimization · severity high · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, ACCESS_HISTORY, QUERY_ATTRIBUTION_HISTORY, TABLES, COLUMNS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $full_reload_query_types = ["CREATE_TABLE_AS_SELECT", "INSERT_OVERWRITE", "TRUNCATE_TABLE"]  (value)
--   $min_bytes_rewritten = 107374182400  (rubric.diagnostics.checks.cost_04.min_bytes_rewritten)
--   $min_reload_day_share = 0.5  (rubric.diagnostics.checks.cost_04.min_reload_day_share)
--   $window_days = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH w AS (
  SELECT ah.OBJECT_NAME, q.QUERY_ID, q.QUERY_PARAMETERIZED_HASH, q.START_TIME, q.BYTES_WRITTEN,
         coalesce(a.CREDITS_ATTRIBUTED_COMPUTE, 0) AS CREDITS
  FROM QUERY_HISTORY q
  JOIN ACCESS_HISTORY ah ON ah.QUERY_ID = q.QUERY_ID AND ah.ACCESS_TYPE = 'WRITE'
  LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = q.QUERY_ID
  WHERE list_contains($full_reload_query_types, q.QUERY_TYPE)),
src AS (
  SELECT w.OBJECT_NAME, min(r.OBJECT_NAME) AS SOURCE_OBJECT
  FROM w JOIN ACCESS_HISTORY r ON r.QUERY_ID = w.QUERY_ID AND r.ACCESS_TYPE = 'READ'
  GROUP BY w.OBJECT_NAME)
SELECT w.OBJECT_NAME, min(w.QUERY_PARAMETERIZED_HASH) AS CLUSTER_KEY,
       count(*) AS RELOADS,
       count(DISTINCT CAST(w.START_TIME AS DATE)) AS RELOAD_DAYS,
       count(DISTINCT CAST(w.START_TIME AS DATE)) / $window_days AS RELOAD_DAY_SHARE,
       avg(w.BYTES_WRITTEN) AS AVG_BYTES_WRITTEN,
       sum(w.BYTES_WRITTEN) AS BYTES_REWRITTEN,
       sum(w.CREDITS) AS CREDITS,
       min(t.BYTES) AS TABLE_BYTES,
       min(src.SOURCE_OBJECT) AS SOURCE_OBJECT,
       (SELECT c.COLUMN_NAME FROM COLUMNS c WHERE c.FQ_NAME = w.OBJECT_NAME AND c.COLUMN_NAME LIKE '%\_ID' ESCAPE '\'
        ORDER BY c.ORDINAL_POSITION LIMIT 1) AS KEY_COLUMN
FROM w
LEFT JOIN TABLES t ON t.FQ_NAME = w.OBJECT_NAME
LEFT JOIN src ON src.OBJECT_NAME = w.OBJECT_NAME
GROUP BY w.OBJECT_NAME
)
SELECT *, coalesce((RELOAD_DAY_SHARE >= $min_reload_day_share AND AVG_BYTES_WRITTEN >= $min_bytes_rewritten), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
