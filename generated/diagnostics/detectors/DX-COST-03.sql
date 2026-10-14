-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-03: Repeated identical queries bypass the result cache
-- Domain D1 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $cache_defeating_pattern = "(?i)(DATEADD\\(\\s*'?(day|week|month|quarter|year)'?\\s*,[^;]*CURRENT_TIMESTAMP|RANDOM\\(|UUID_STRING\\(|RANDSTR\\()"  (value)
--   $max_result_reuse_share = 0.2  (rubric.diagnostics.checks.cost_03.max_result_reuse_share)
--   $min_repeat_executions = 500  (rubric.diagnostics.checks.cost_03.min_repeat_executions)
WITH __signals AS (
SELECT q.QUERY_PARAMETERIZED_HASH AS OBJECT_NAME, q.QUERY_PARAMETERIZED_HASH AS CLUSTER_KEY,
       min(q.WAREHOUSE_NAME) AS WAREHOUSE_NAME,
       count(*) AS EXECUTIONS,
       count(DISTINCT q.QUERY_TEXT) AS DISTINCT_TEXTS,
       avg(CASE WHEN q.BYTES_SCANNED = 0 THEN 1 ELSE 0 END) AS RESULT_REUSE_SHARE,
       max(CASE WHEN regexp_matches(q.QUERY_TEXT, $cache_defeating_pattern) THEN 1 ELSE 0 END) AS CACHE_DEFEATING,
       coalesce(sum(a.CREDITS_ATTRIBUTED_COMPUTE), 0) AS CREDITS,
       min(q.QUERY_TEXT) AS SAMPLE_TEXT
FROM QUERY_HISTORY q
LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = q.QUERY_ID
WHERE q.QUERY_TYPE = 'SELECT' AND q.EXECUTION_STATUS = 'SUCCESS'
GROUP BY q.QUERY_PARAMETERIZED_HASH
)
SELECT *, coalesce((DISTINCT_TEXTS = 1 AND EXECUTIONS >= $min_repeat_executions AND RESULT_REUSE_SHARE <= $max_result_reuse_share AND CACHE_DEFEATING = 1), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
