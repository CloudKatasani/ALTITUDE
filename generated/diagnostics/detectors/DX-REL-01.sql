-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/rel.yaml. Regenerate with `altitude generate`.
-- DX-REL-01: Failing or retried tasks
-- Domain D3 · WAF pillar reliability · severity high · last verified 2026-10-01
-- Source tables: TASKS, TASK_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $max_failure_rate = 0.05  (rubric.diagnostics.checks.rel_01.max_failure_rate)
--   $max_recursion = 64  (rubric.diagnostics.window.max_recursion_depth)
--   $min_failures = 3  (rubric.diagnostics.checks.rel_01.min_failures)
WITH __signals AS (
WITH RECURSIVE edges AS (
  SELECT trim(p.PRED) AS PARENT, t.FQ_NAME AS CHILD
  FROM TASKS t, unnest(string_split(t.PREDECESSORS, ',')) AS p(PRED)
  WHERE t.PREDECESSORS IS NOT NULL),
down AS (
  SELECT PARENT AS ROOT, CHILD, 1 AS DEPTH FROM edges
  UNION ALL
  SELECT d.ROOT, e.CHILD, d.DEPTH + 1 FROM down d JOIN edges e ON e.PARENT = d.CHILD WHERE d.DEPTH < $max_recursion),
up AS (
  SELECT CHILD AS TASK, PARENT AS ANCESTOR, 1 AS DEPTH FROM edges
  UNION ALL
  SELECT u.TASK, e.PARENT, u.DEPTH + 1 FROM up u JOIN edges e ON e.CHILD = u.ANCESTOR WHERE u.DEPTH < $max_recursion),
h AS (
  SELECT FQ_NAME, count(*) AS RUNS,
         count(*) FILTER (WHERE STATE = 'FAILED') AS FAILURES,
         count(*) FILTER (WHERE ATTEMPT_NUMBER > 1) AS RETRIES,
         max(ERROR_MESSAGE) AS LAST_ERROR
  FROM TASK_HISTORY GROUP BY FQ_NAME),
blast AS (
  SELECT d.ROOT, string_agg(DISTINCT d.CHILD, ', ' ORDER BY d.CHILD) AS DOWNSTREAM_TASKS,
         count(DISTINCT d.CHILD) AS DOWNSTREAM_COUNT
  FROM down d GROUP BY d.ROOT),
skipped AS (
  SELECT d.ROOT, count(*) AS DOWNSTREAM_SKIPPED_RUNS
  FROM down d JOIN TASK_HISTORY th ON th.FQ_NAME = d.CHILD AND th.STATE = 'SKIPPED' GROUP BY d.ROOT)
SELECT t.FQ_NAME AS OBJECT_NAME,
       coalesce((SELECT max(u.ANCESTOR) FROM up u WHERE u.TASK = t.FQ_NAME
                 AND u.DEPTH = (SELECT max(u2.DEPTH) FROM up u2 WHERE u2.TASK = t.FQ_NAME)), t.FQ_NAME) AS CLUSTER_KEY,
       t.WAREHOUSE, t.TARGET_TABLE, t.PREDECESSORS,
       coalesce(h.RUNS, 0) AS RUNS, coalesce(h.FAILURES, 0) AS FAILURES, coalesce(h.RETRIES, 0) AS RETRIES,
       CASE WHEN coalesce(h.RUNS, 0) > 0 THEN h.FAILURES / h.RUNS ELSE 0 END AS FAILURE_RATE,
       h.LAST_ERROR, b.DOWNSTREAM_TASKS, coalesce(b.DOWNSTREAM_COUNT, 0) AS DOWNSTREAM_COUNT,
       coalesce(s.DOWNSTREAM_SKIPPED_RUNS, 0) AS DOWNSTREAM_SKIPPED_RUNS
FROM TASKS t
LEFT JOIN h ON h.FQ_NAME = t.FQ_NAME
LEFT JOIN blast b ON b.ROOT = t.FQ_NAME
LEFT JOIN skipped s ON s.ROOT = t.FQ_NAME
)
SELECT *, coalesce((FAILURE_RATE >= $max_failure_rate AND FAILURES >= $min_failures), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
