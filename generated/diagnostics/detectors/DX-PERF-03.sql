-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/perf.yaml. Regenerate with `altitude generate`.
-- DX-PERF-03: Poor pruning on large, frequently filtered tables
-- Domain D2 · WAF pillar performance_efficiency · severity medium · last verified 2026-10-01
-- Source tables: TABLES, ACCESS_HISTORY, QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY, COLUMNS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $bytes_per_tb = <bound by the engine from the snapshot / rubric units>
--   $clustering_candidate_pattern = "(?i)_DATE$"  (value)
--   $min_partitions_total = 10000  (rubric.diagnostics.checks.perf_03.min_partitions_total)
--   $min_poor_pruning_scans = 100  (rubric.diagnostics.checks.perf_03.min_poor_pruning_scans)
--   $min_table_bytes = 1099511627776  (rubric.diagnostics.checks.perf_03.min_table_bytes)
--   $poor_pruning_ratio = 0.8  (rubric.diagnostics.checks.perf_03.poor_pruning_ratio)
WITH __signals AS (
WITH r AS (
  SELECT ah.OBJECT_NAME, q.QUERY_ID, q.PARTITIONS_SCANNED, q.PARTITIONS_TOTAL,
         coalesce(a.CREDITS_ATTRIBUTED_COMPUTE, 0) AS CREDITS
  FROM ACCESS_HISTORY ah
  JOIN QUERY_HISTORY q ON q.QUERY_ID = ah.QUERY_ID
  LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = q.QUERY_ID
  WHERE ah.ACCESS_TYPE = 'READ' AND q.PARTITIONS_TOTAL >= $min_partitions_total)
SELECT t.FQ_NAME AS OBJECT_NAME, t.FQ_NAME AS CLUSTER_KEY, t.BYTES AS TABLE_BYTES,
       t.BYTES / $bytes_per_tb AS TABLE_TB, t.CLUSTERING_KEY,
       count(r.QUERY_ID) AS LARGE_SCANS,
       count(r.QUERY_ID) FILTER (WHERE r.PARTITIONS_SCANNED >= $poor_pruning_ratio * r.PARTITIONS_TOTAL) AS POOR_PRUNING_SCANS,
       coalesce(sum(r.CREDITS) FILTER (WHERE r.PARTITIONS_SCANNED >= $poor_pruning_ratio * r.PARTITIONS_TOTAL), 0) AS POOR_PRUNING_CREDITS,
       (SELECT min(c.COLUMN_NAME) FROM COLUMNS c WHERE c.FQ_NAME = t.FQ_NAME
        AND regexp_matches(c.COLUMN_NAME, $clustering_candidate_pattern)) AS SUGGESTED_KEY
FROM TABLES t LEFT JOIN r ON r.OBJECT_NAME = t.FQ_NAME
GROUP BY t.FQ_NAME, t.BYTES, t.CLUSTERING_KEY
)
SELECT *, coalesce((CLUSTERING_KEY IS NULL AND TABLE_BYTES >= $min_table_bytes AND POOR_PRUNING_SCANS >= $min_poor_pruning_scans), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
