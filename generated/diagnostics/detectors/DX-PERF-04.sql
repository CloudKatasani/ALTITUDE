-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/perf.yaml. Regenerate with `altitude generate`.
-- DX-PERF-04: Costly query signatures with anti-patterns
-- Domain D2 · WAF pillar performance_efficiency · severity medium · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $exploding_rows_min = 100000000  (rubric.diagnostics.checks.perf_04.exploding_rows_min)
--   $min_anti_patterns = 2  (rubric.diagnostics.checks.perf_04.min_anti_patterns)
--   $non_sargable_pattern = "(?i)where\\s+(to_char|to_varchar|upper|lower|trim|cast|date_trunc)\\s*\\("  (value)
--   $select_star_join_pattern = "(?is)select\\s+\\*.*\\bjoin\\b"  (value)
--   $top_n_signatures = 10  (rubric.diagnostics.checks.perf_04.top_n_signatures)
WITH __signals AS (
WITH sig AS (
  SELECT q.QUERY_PARAMETERIZED_HASH AS H, min(q.QUERY_TEXT) AS SAMPLE_TEXT, min(q.WAREHOUSE_NAME) AS WAREHOUSE_NAME,
         count(*) AS EXECUTIONS, avg(q.ROWS_PRODUCED) AS AVG_ROWS_PRODUCED, avg(q.EXECUTION_TIME) AS AVG_EXECUTION_MS,
         coalesce(sum(a.CREDITS_ATTRIBUTED_COMPUTE), 0) AS CREDITS
  FROM QUERY_HISTORY q LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = q.QUERY_ID
  WHERE q.QUERY_TYPE = 'SELECT'
  GROUP BY q.QUERY_PARAMETERIZED_HASH),
flags AS (
  SELECT *, rank() OVER (ORDER BY CREDITS DESC) AS COST_RANK,
         CASE WHEN regexp_matches(SAMPLE_TEXT, $select_star_join_pattern) THEN 1 ELSE 0 END AS SELECT_STAR_JOIN,
         CASE WHEN regexp_matches(SAMPLE_TEXT, $non_sargable_pattern) THEN 1 ELSE 0 END AS NON_SARGABLE,
         CASE WHEN AVG_ROWS_PRODUCED >= $exploding_rows_min THEN 1 ELSE 0 END AS EXPLODING_JOIN
  FROM sig)
SELECT H AS OBJECT_NAME, H AS CLUSTER_KEY, WAREHOUSE_NAME, EXECUTIONS, AVG_ROWS_PRODUCED, AVG_EXECUTION_MS, CREDITS,
       COST_RANK, SELECT_STAR_JOIN, NON_SARGABLE, EXPLODING_JOIN,
       SELECT_STAR_JOIN + NON_SARGABLE + EXPLODING_JOIN AS ANTI_PATTERNS, SAMPLE_TEXT
FROM flags
)
SELECT *, coalesce((COST_RANK <= $top_n_signatures AND ANTI_PATTERNS >= $min_anti_patterns), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
