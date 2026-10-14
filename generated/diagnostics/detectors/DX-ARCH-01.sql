-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/arch.yaml. Regenerate with `altitude generate`.
-- DX-ARCH-01: Deep view stacks and duplicate tables
-- Domain D7 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: VIEWS, OBJECT_DEPENDENCIES, TABLES, TABLE_STORAGE_METRICS, ACCESS_HISTORY, QUERY_ATTRIBUTION_HISTORY, CLIENT_INPUTS, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $bytes_per_tb = <bound by the engine from the snapshot / rubric units>
--   $max_recursion = 64  (rubric.diagnostics.window.max_recursion_depth)
--   $max_view_depth = 5  (rubric.diagnostics.checks.arch_01.max_view_depth)
--   $min_size_similarity = 0.95  (rubric.diagnostics.checks.arch_01.min_size_similarity)
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
WITH RECURSIVE vdep AS (
  SELECT REFERENCING_OBJECT_NAME AS V, REFERENCED_OBJECT_NAME AS R, 1 AS DEPTH
  FROM OBJECT_DEPENDENCIES WHERE upper(REFERENCING_OBJECT_DOMAIN) = 'VIEW'
  UNION ALL
  SELECT d.V, o.REFERENCED_OBJECT_NAME, d.DEPTH + 1
  FROM vdep d JOIN OBJECT_DEPENDENCIES o
    ON o.REFERENCING_OBJECT_NAME = d.R AND upper(o.REFERENCING_OBJECT_DOMAIN) = 'VIEW'
  WHERE d.DEPTH < $max_recursion),
depth AS (SELECT V, max(DEPTH) AS VIEW_DEPTH FROM vdep GROUP BY V),
reads AS (
  SELECT ah.OBJECT_NAME, coalesce(sum(a.CREDITS_ATTRIBUTED_COMPUTE), 0) AS READ_CREDITS
  FROM ACCESS_HISTORY ah LEFT JOIN QUERY_ATTRIBUTION_HISTORY a ON a.QUERY_ID = ah.QUERY_ID
  WHERE ah.ACCESS_TYPE = 'READ' GROUP BY ah.OBJECT_NAME),
t AS (
  SELECT tb.FQ_NAME, tb.TABLE_ID, tb.CREATED, tb.BYTES, tb.ROW_COUNT, tb.COLUMN_SIGNATURE,
         CASE WHEN tb.FQ_NAME IN (SELECT FQ_NAME FROM _TIER1_TABLES) THEN 1 ELSE 0 END AS IS_TIER1,
         coalesce(s.ACTIVE_BYTES, 0) + coalesce(s.TIME_TRAVEL_BYTES, 0) + coalesce(s.FAILSAFE_BYTES, 0) AS STORAGE_BYTES
  FROM TABLES tb LEFT JOIN TABLE_STORAGE_METRICS s ON s.FQ_NAME = tb.FQ_NAME),
dup AS (
  SELECT b.FQ_NAME, min(a.FQ_NAME) AS DUPLICATE_OF
  FROM t a JOIN t b
    ON a.COLUMN_SIGNATURE = b.COLUMN_SIGNATURE AND a.FQ_NAME <> b.FQ_NAME
   AND least(a.BYTES, b.BYTES) >= $min_size_similarity * greatest(a.BYTES, b.BYTES)
   AND least(a.ROW_COUNT, b.ROW_COUNT) >= $min_size_similarity * greatest(a.ROW_COUNT, b.ROW_COUNT)
  WHERE a.IS_TIER1 > b.IS_TIER1
     OR (a.IS_TIER1 = b.IS_TIER1 AND (a.CREATED < b.CREATED OR (a.CREATED = b.CREATED AND a.TABLE_ID < b.TABLE_ID)))
  GROUP BY b.FQ_NAME)
SELECT v.FQ_NAME AS OBJECT_NAME, 'view_depth' AS CLUSTER_KEY,
       coalesce(depth.VIEW_DEPTH, 0) AS VIEW_DEPTH,
       CASE WHEN NOT EXISTS (SELECT 1 FROM OBJECT_DEPENDENCIES o WHERE o.REFERENCED_OBJECT_NAME = v.FQ_NAME) THEN 1 ELSE 0 END AS IS_LEAF,
       NULL::VARCHAR AS DUPLICATE_OF, 0::DOUBLE AS DUPLICATE_TB,
       coalesce(reads.READ_CREDITS, 0) AS READ_CREDITS
FROM VIEWS v LEFT JOIN depth ON depth.V = v.FQ_NAME LEFT JOIN reads ON reads.OBJECT_NAME = v.FQ_NAME
UNION ALL
SELECT t.FQ_NAME, 'duplicate_table', NULL, NULL, dup.DUPLICATE_OF,
       CASE WHEN dup.DUPLICATE_OF IS NULL THEN 0 ELSE t.STORAGE_BYTES / $bytes_per_tb END, 0
FROM t LEFT JOIN dup ON dup.FQ_NAME = t.FQ_NAME
)
SELECT *, coalesce(((CLUSTER_KEY = 'view_depth' AND IS_LEAF = 1 AND VIEW_DEPTH > $max_view_depth) OR (CLUSTER_KEY = 'duplicate_table' AND DUPLICATE_OF IS NOT NULL)), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
