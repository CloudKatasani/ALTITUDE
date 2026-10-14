-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/perf.yaml. Regenerate with `altitude generate`.
-- DX-PERF-01: Queueing on interactive warehouses at peak
-- Domain D2 · WAF pillar performance_efficiency · severity high · last verified 2026-10-01
-- Source tables: WAREHOUSES, WAREHOUSE_LOAD_HISTORY, QUERY_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $interactive_workload_classes = ["bi", "adhoc", "agents"]  (value)
--   $min_queued_hours = 10  (rubric.diagnostics.checks.perf_01.min_queued_hours)
--   $ms_per_hour = <bound by the engine from the snapshot / rubric units>
--   $queued_load_min = 0.5  (rubric.diagnostics.checks.perf_01.queued_load_min)
--   $target_max_cluster_count = 3  (rubric.diagnostics.checks.perf_01.target_max_cluster_count)
WITH __signals AS (
WITH l AS (
  SELECT WAREHOUSE_NAME,
         count(*) FILTER (WHERE AVG_QUEUED_LOAD >= $queued_load_min) AS QUEUED_HOURS,
         max(AVG_QUEUED_LOAD) AS MAX_QUEUED_LOAD
  FROM WAREHOUSE_LOAD_HISTORY GROUP BY WAREHOUSE_NAME),
q AS (
  SELECT WAREHOUSE_NAME, sum(QUEUED_OVERLOAD_TIME) / $ms_per_hour AS USER_HOURS_QUEUED,
         count(*) FILTER (WHERE QUEUED_OVERLOAD_TIME > 0) AS QUEUED_QUERIES
  FROM QUERY_HISTORY GROUP BY WAREHOUSE_NAME)
SELECT w.WAREHOUSE_NAME AS OBJECT_NAME, w.WAREHOUSE_NAME AS CLUSTER_KEY, w.WORKLOAD_CLASS,
       w.MIN_CLUSTER_COUNT, w.MAX_CLUSTER_COUNT, w.SCALING_POLICY,
       CASE WHEN list_contains($interactive_workload_classes, w.WORKLOAD_CLASS) THEN 1 ELSE 0 END AS INTERACTIVE,
       coalesce(l.QUEUED_HOURS, 0) AS QUEUED_HOURS, coalesce(l.MAX_QUEUED_LOAD, 0) AS MAX_QUEUED_LOAD,
       coalesce(q.USER_HOURS_QUEUED, 0) AS USER_HOURS_QUEUED, coalesce(q.QUEUED_QUERIES, 0) AS QUEUED_QUERIES
FROM WAREHOUSES w
LEFT JOIN l ON l.WAREHOUSE_NAME = w.WAREHOUSE_NAME
LEFT JOIN q ON q.WAREHOUSE_NAME = w.WAREHOUSE_NAME
)
SELECT *, coalesce((INTERACTIVE = 1 AND QUEUED_HOURS >= $min_queued_hours AND MAX_CLUSTER_COUNT < $target_max_cluster_count), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
