-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-02: Oversized warehouses
-- Domain D1 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: WAREHOUSES, WAREHOUSE_METERING_HISTORY, WAREHOUSE_LOAD_HISTORY, QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $exec_quantile = 0.95  (rubric.diagnostics.checks.cost_02.exec_quantile)
--   $max_avg_queued_load = 0.05  (rubric.diagnostics.checks.cost_02.max_avg_queued_load)
--   $max_p95_exec_ms = 10000  (rubric.diagnostics.checks.cost_02.max_p95_exec_ms)
--   $min_size_credits = 4  (rubric.diagnostics.checks.cost_02.min_size_credits)
-- Helper _SIZE_CREDITS (HLP-SIZE-CREDITS): Credits per hour per cluster for each warehouse size.
-- Helper _WAREHOUSE_CREDITS (HLP-WH-CREDITS): Billed vs query-attributed compute credits per warehouse over the snapshot window.
WITH __signals AS (
WITH q AS (
  SELECT WAREHOUSE_NAME, count(*) AS QUERIES,
         quantile_cont(EXECUTION_TIME, $exec_quantile) AS EXEC_P95_MS
  FROM QUERY_HISTORY WHERE WAREHOUSE_NAME IS NOT NULL GROUP BY WAREHOUSE_NAME),
l AS (
  SELECT WAREHOUSE_NAME, avg(AVG_QUEUED_LOAD) AS AVG_QUEUED_LOAD
  FROM WAREHOUSE_LOAD_HISTORY GROUP BY WAREHOUSE_NAME)
SELECT w.WAREHOUSE_NAME AS OBJECT_NAME, w.WAREHOUSE_NAME AS CLUSTER_KEY,
       w.WAREHOUSE_SIZE, w.WORKLOAD_CLASS, s.CREDITS_PER_HOUR,
       (SELECT t.WAREHOUSE_SIZE FROM _SIZE_CREDITS t WHERE t.CREDITS_PER_HOUR < s.CREDITS_PER_HOUR
        ORDER BY t.CREDITS_PER_HOUR DESC LIMIT 1) AS TARGET_SIZE,
       (SELECT max(t.CREDITS_PER_HOUR) FROM _SIZE_CREDITS t WHERE t.CREDITS_PER_HOUR < s.CREDITS_PER_HOUR) AS TARGET_CREDITS_PER_HOUR,
       coalesce(q.QUERIES, 0) AS QUERIES, coalesce(q.EXEC_P95_MS, 0) AS EXEC_P95_MS,
       coalesce(l.AVG_QUEUED_LOAD, 0) AS AVG_QUEUED_LOAD, c.BILLED_CREDITS,
       w.MAX_CLUSTER_COUNT,
       c.BILLED_CREDITS * (1 - coalesce((SELECT max(t.CREDITS_PER_HOUR) FROM _SIZE_CREDITS t
            WHERE t.CREDITS_PER_HOUR < s.CREDITS_PER_HOUR), s.CREDITS_PER_HOUR) / s.CREDITS_PER_HOUR) AS DOWNSIZE_CREDITS
FROM WAREHOUSES w
JOIN _SIZE_CREDITS s ON s.WAREHOUSE_SIZE = w.WAREHOUSE_SIZE
JOIN _WAREHOUSE_CREDITS c ON c.WAREHOUSE_NAME = w.WAREHOUSE_NAME
LEFT JOIN q ON q.WAREHOUSE_NAME = w.WAREHOUSE_NAME
LEFT JOIN l ON l.WAREHOUSE_NAME = w.WAREHOUSE_NAME
)
SELECT *, coalesce((CREDITS_PER_HOUR >= $min_size_credits AND QUERIES > 0 AND EXEC_P95_MS <= $max_p95_exec_ms AND AVG_QUEUED_LOAD <= $max_avg_queued_load AND MAX_CLUSTER_COUNT <= 1 AND TARGET_SIZE IS NOT NULL), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
