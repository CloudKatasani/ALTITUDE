-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/ops.yaml. Regenerate with `altitude generate`.
-- DX-OPS-01: Production DDL outside IaC/CI
-- Domain D6 · WAF pillar operational_excellence · severity medium · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, CLIENT_INPUTS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $ddl_query_type_pattern = "^(CREATE|ALTER|DROP|RENAME)_"  (value)
--   $iac_pattern = "(?i)(terraform|schemachange|dbt|flyway|liquibase|github|gitlab|azure ?devops|ci)"  (value)
--   $min_ddl_statements = 3  (rubric.diagnostics.checks.ops_01.min_ddl_statements)
--   $min_iac_share = 0.8  (rubric.diagnostics.checks.ops_01.min_iac_share)
--   $non_ddl_query_types = ["CREATE_TABLE_AS_SELECT"]  (value)
WITH __signals AS (
WITH prod AS (
  SELECT unnest(from_json(VALUE, '["VARCHAR"]')) AS DB FROM CLIENT_INPUTS WHERE KEY = 'production_databases')
SELECT q.USER_NAME AS OBJECT_NAME, q.USER_NAME AS CLUSTER_KEY,
       count(*) AS DDL_STATEMENTS,
       count(DISTINCT CAST(q.START_TIME AS DATE)) AS DDL_DAYS,
       avg(CASE WHEN regexp_matches(coalesce(q.QUERY_TAG, '') || ' ' || coalesce(q.CLIENT_APPLICATION_ID, ''), $iac_pattern)
                THEN 1 ELSE 0 END) AS IAC_SHARE,
       string_agg(DISTINCT q.QUERY_TYPE, ', ' ORDER BY q.QUERY_TYPE) AS DDL_TYPES,
       string_agg(DISTINCT q.CLIENT_APPLICATION_ID, ', ' ORDER BY q.CLIENT_APPLICATION_ID) AS CLIENT_APPS
FROM QUERY_HISTORY q
WHERE regexp_matches(q.QUERY_TYPE, $ddl_query_type_pattern)
  AND NOT list_contains($non_ddl_query_types, q.QUERY_TYPE)
  AND (q.DATABASE_NAME IN (SELECT DB FROM prod) OR NOT EXISTS (SELECT 1 FROM prod))
GROUP BY q.USER_NAME
)
SELECT *, coalesce((IAC_SHARE < $min_iac_share AND DDL_STATEMENTS >= $min_ddl_statements), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
