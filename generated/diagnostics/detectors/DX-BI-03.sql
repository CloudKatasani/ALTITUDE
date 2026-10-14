-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/bi.yaml. Regenerate with `altitude generate`.
-- DX-BI-03: Dashboards whose refresh cost exceeds their use
-- Domain D8 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: BI_REPORTS, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $max_cost_per_view_usd = 5  (rubric.diagnostics.checks.bi_03.max_cost_per_view_usd)
--   $price_per_credit = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH sig AS (
  SELECT QUERY_PARAMETERIZED_HASH, sum(CREDITS_ATTRIBUTED_COMPUTE) AS CREDITS
  FROM QUERY_ATTRIBUTION_HISTORY GROUP BY QUERY_PARAMETERIZED_HASH),
r AS (
  SELECT b.*,
         CASE WHEN sum(b.REFRESHES_PER_DAY) OVER (PARTITION BY b.QUERY_PARAMETERIZED_HASH) > 0
              THEN b.REFRESHES_PER_DAY / sum(b.REFRESHES_PER_DAY) OVER (PARTITION BY b.QUERY_PARAMETERIZED_HASH)
              ELSE 0 END AS REFRESH_SHARE
  FROM BI_REPORTS b)
SELECT r.REPORT_ID AS OBJECT_NAME, r.REPORT_ID AS CLUSTER_KEY, r.TOOL, r.NAME, r.OWNER, r.VIEWS_90D, r.REFRESHES_PER_DAY,
       r.QUERY_PARAMETERIZED_HASH,
       coalesce(sig.CREDITS, 0) * r.REFRESH_SHARE AS REPORT_CREDITS,
       coalesce(sig.CREDITS, 0) * r.REFRESH_SHARE * $price_per_credit / greatest(r.VIEWS_90D, 1) AS COST_PER_VIEW_USD
FROM r LEFT JOIN sig ON sig.QUERY_PARAMETERIZED_HASH = r.QUERY_PARAMETERIZED_HASH
)
SELECT *, coalesce((COST_PER_VIEW_USD >= $max_cost_per_view_usd), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
