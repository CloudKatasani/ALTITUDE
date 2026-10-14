-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-08: Capacity commitment mis-sized
-- Domain D1 · WAF pillar cost_optimization · severity high · last verified 2026-10-01
-- Source tables: METERING_DAILY_HISTORY, CLIENT_INPUTS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $days_per_year = <bound by the engine from the snapshot / rubric units>
--   $max_commit_variance = 0.15  (rubric.diagnostics.checks.cost_08.max_commit_variance)
--   $window_days = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH m AS (SELECT sum(CREDITS_BILLED) AS WINDOW_CREDITS FROM METERING_DAILY_HISTORY),
c AS (SELECT CAST(VALUE ->> 'annual_credits' AS DOUBLE) AS COMMIT_CREDITS FROM CLIENT_INPUTS WHERE KEY = 'capacity_commitment')
SELECT 'ACCOUNT' AS OBJECT_NAME, 'capacity' AS CLUSTER_KEY, m.WINDOW_CREDITS,
       m.WINDOW_CREDITS / $window_days * $days_per_year AS FORECAST_ANNUAL_CREDITS,
       c.COMMIT_CREDITS,
       (c.COMMIT_CREDITS - m.WINDOW_CREDITS / $window_days * $days_per_year) / c.COMMIT_CREDITS AS COMMIT_VARIANCE,
       greatest(c.COMMIT_CREDITS - m.WINDOW_CREDITS / $window_days * $days_per_year, 0) AS OVER_COMMIT_CREDITS,
       greatest(m.WINDOW_CREDITS / $window_days * $days_per_year - c.COMMIT_CREDITS, 0) AS OVERAGE_CREDITS
FROM m CROSS JOIN c WHERE c.COMMIT_CREDITS > 0
)
SELECT *, coalesce((abs(COMMIT_VARIANCE) >= $max_commit_variance), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
