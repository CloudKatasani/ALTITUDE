-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/bi.yaml. Regenerate with `altitude generate`.
-- DX-BI-02: Conflicting KPI definitions
-- Domain D8 · WAF pillar security_governance · severity high · last verified 2026-10-01
-- Source tables: BI_MEASURES, TABLES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
WITH __signals AS (
WITH m AS (
  SELECT KPI_NAME, REPORT_ID, EXPRESSION, SOURCE_COLUMNS,
         upper(regexp_replace(EXPRESSION, '\s+', '', 'g')) AS NORM_EXPR
  FROM BI_MEASURES),
votes AS (
  SELECT KPI_NAME, NORM_EXPR, min(EXPRESSION) AS EXPRESSION, count(DISTINCT REPORT_ID) AS REPORTS,
         min(SOURCE_COLUMNS) AS SOURCE_COLUMNS,
         row_number() OVER (PARTITION BY KPI_NAME ORDER BY count(DISTINCT REPORT_ID) DESC, NORM_EXPR) AS RN
  FROM m GROUP BY KPI_NAME, NORM_EXPR)
SELECT m.KPI_NAME AS OBJECT_NAME, m.KPI_NAME AS CLUSTER_KEY,
       count(DISTINCT m.NORM_EXPR) AS DEFINITIONS,
       count(DISTINCT m.REPORT_ID) AS REPORTS,
       string_agg(DISTINCT m.EXPRESSION, ' | ' ORDER BY m.EXPRESSION) AS VARIANTS,
       string_agg(DISTINCT m.REPORT_ID, ', ' ORDER BY m.REPORT_ID) AS REPORT_IDS,
       min(v.EXPRESSION) AS CERTIFIED_EXPRESSION,
       (SELECT min(t.FQ_NAME) FROM TABLES t WHERE t.TABLE_NAME = split_part(min(v.SOURCE_COLUMNS), '.', 1)) AS CERTIFIED_TABLE
FROM m JOIN votes v ON v.KPI_NAME = m.KPI_NAME AND v.RN = 1
GROUP BY m.KPI_NAME
)
SELECT *, coalesce((DEFINITIONS > 1), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
