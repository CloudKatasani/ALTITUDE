-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/perf.yaml. Regenerate with `altitude generate`.
-- DX-PERF-02: Spilling to local or remote storage
-- Domain D2 · WAF pillar performance_efficiency · severity medium · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $min_avg_local_spill_bytes = 53687091200  (rubric.diagnostics.checks.perf_02.min_avg_local_spill_bytes)
--   $min_avg_remote_spill_bytes = 1073741824  (rubric.diagnostics.checks.perf_02.min_avg_remote_spill_bytes)
-- Helper _SIZE_CREDITS (HLP-SIZE-CREDITS): Credits per hour per cluster for each warehouse size.
WITH __signals AS (
SELECT q.QUERY_PARAMETERIZED_HASH AS OBJECT_NAME, q.QUERY_PARAMETERIZED_HASH AS CLUSTER_KEY,
       min(q.WAREHOUSE_NAME) AS WAREHOUSE_NAME, min(q.WAREHOUSE_SIZE) AS WAREHOUSE_SIZE,
       count(*) AS EXECUTIONS,
       avg(q.BYTES_SPILLED_TO_LOCAL_STORAGE) AS AVG_LOCAL_SPILL_BYTES,
       avg(q.BYTES_SPILLED_TO_REMOTE_STORAGE) AS AVG_REMOTE_SPILL_BYTES,
       avg(q.EXECUTION_TIME) AS AVG_EXECUTION_MS,
       coalesce(sum(a.CREDITS_ATTRIBUTED_COMPUTE), 0) AS CREDITS,
       (SELECT t.WAREHOUSE_SIZE FROM _SIZE_CREDITS t
        WHERE t.CREDITS_PER_HOUR > (SELECT s.CREDITS_PER_HOUR FROM _SIZE_CREDITS s WHERE s.WAREHOUSE_SIZE = min(q.WAREHOUSE_SIZE))
        ORDER BY t.CREDITS_PER_HOUR LIMIT 1) AS TARGET_SIZE
FROM QUERY_HISTORY q
LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = q.QUERY_ID
WHERE q.WAREHOUSE_NAME IS NOT NULL
GROUP BY q.QUERY_PARAMETERIZED_HASH
)
SELECT *, coalesce((AVG_REMOTE_SPILL_BYTES >= $min_avg_remote_spill_bytes OR AVG_LOCAL_SPILL_BYTES >= $min_avg_local_spill_bytes), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
