-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-05: Serverless creep without benefit
-- Domain D1 · WAF pillar cost_optimization · severity high · last verified 2026-10-01
-- Source tables: AUTOMATIC_CLUSTERING_HISTORY, SEARCH_OPTIMIZATION_HISTORY, MATERIALIZED_VIEW_REFRESH_HISTORY, ACCESS_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $days_per_month = <bound by the engine from the snapshot / rubric units>
--   $max_reads_per_credit = 1  (rubric.diagnostics.checks.cost_05.max_reads_per_credit)
--   $min_monthly_credits = 100  (rubric.diagnostics.checks.cost_05.min_monthly_credits)
--   $window_days = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH s AS (
  SELECT TABLE_NAME, 'AUTOMATIC_CLUSTERING' AS FEATURE, CREDITS_USED FROM AUTOMATIC_CLUSTERING_HISTORY
  UNION ALL SELECT TABLE_NAME, 'SEARCH_OPTIMIZATION', CREDITS_USED FROM SEARCH_OPTIMIZATION_HISTORY
  UNION ALL SELECT TABLE_NAME, 'MATERIALIZED_VIEW', CREDITS_USED FROM MATERIALIZED_VIEW_REFRESH_HISTORY),
agg AS (SELECT TABLE_NAME, FEATURE, sum(CREDITS_USED) AS CREDITS FROM s GROUP BY TABLE_NAME, FEATURE),
r AS (SELECT OBJECT_NAME, count(*) AS READS FROM ACCESS_HISTORY WHERE ACCESS_TYPE = 'READ' GROUP BY OBJECT_NAME)
SELECT agg.TABLE_NAME AS OBJECT_NAME, agg.TABLE_NAME || ':' || agg.FEATURE AS CLUSTER_KEY, agg.FEATURE,
       agg.CREDITS, agg.CREDITS / $window_days * $days_per_month AS CREDITS_PER_MONTH,
       coalesce(r.READS, 0) AS READS,
       CASE WHEN agg.CREDITS > 0 THEN coalesce(r.READS, 0) / agg.CREDITS ELSE 0 END AS READS_PER_CREDIT
FROM agg LEFT JOIN r ON r.OBJECT_NAME = agg.TABLE_NAME
)
SELECT *, coalesce((CREDITS_PER_MONTH >= $min_monthly_credits AND READS_PER_CREDIT <= $max_reads_per_credit), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
