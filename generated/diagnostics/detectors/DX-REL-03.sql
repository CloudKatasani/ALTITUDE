-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/rel.yaml. Regenerate with `altitude generate`.
-- DX-REL-03: Pipelines running under personal credentials
-- Domain D3 · WAF pillar reliability · severity high · last verified 2026-10-01
-- Source tables: QUERY_HISTORY, USERS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $min_recurring_days = 20  (rubric.diagnostics.checks.rel_03.min_recurring_days)
--   $pipeline_query_types = ["INSERT", "MERGE", "UPDATE", "DELETE", "COPY", "CREATE_TABLE_AS_SELECT", "INSERT_OVERWRITE"]  (value)
WITH __signals AS (
SELECT q.USER_NAME AS OBJECT_NAME, q.USER_NAME AS CLUSTER_KEY,
       coalesce(min(u.TYPE), 'PERSON') AS USER_TYPE,
       count(*) AS EXECUTIONS,
       count(DISTINCT CAST(q.START_TIME AS DATE)) AS RUN_DAYS,
       string_agg(DISTINCT q.QUERY_PARAMETERIZED_HASH, ', ' ORDER BY q.QUERY_PARAMETERIZED_HASH) AS SIGNATURES,
       string_agg(DISTINCT coalesce(q.QUERY_TAG, '(none)'), ', ' ORDER BY coalesce(q.QUERY_TAG, '(none)')) AS QUERY_TAGS,
       string_agg(DISTINCT q.CLIENT_APPLICATION_ID, ', ' ORDER BY q.CLIENT_APPLICATION_ID) AS CLIENT_APPS,
       min(q.ROLE_NAME) AS ROLE_NAME,
       upper(regexp_replace(coalesce(min(q.QUERY_TAG), q.USER_NAME), '[^A-Za-z0-9]+', '_', 'g')) AS PIPELINE_ID
FROM QUERY_HISTORY q LEFT JOIN USERS u ON u.NAME = q.USER_NAME
WHERE list_contains($pipeline_query_types, q.QUERY_TYPE)
GROUP BY q.USER_NAME
)
SELECT *, coalesce((USER_TYPE = 'PERSON' AND RUN_DAYS >= $min_recurring_days), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
