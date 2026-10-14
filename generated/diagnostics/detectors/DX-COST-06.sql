-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-06: Storage waste
-- Domain D1 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: TABLES, TABLE_STORAGE_METRICS, ACCESS_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $as_of = <bound by the engine from the snapshot / rubric units>
--   $bytes_per_tb = <bound by the engine from the snapshot / rubric units>
--   $min_wasted_bytes = 10737418240  (rubric.diagnostics.checks.cost_06.min_wasted_bytes)
--   $staging_max_retention_days = 1  (rubric.diagnostics.checks.cost_06.staging_max_retention_days)
--   $staging_schema_pattern = "(?i)^(STAGING|STG|STAGE|LANDING|TMP|TEMP|WORK)$"  (value)
--   $stale_clone_days = 180  (rubric.diagnostics.checks.cost_06.stale_clone_days)
WITH __signals AS (
WITH m AS (
  SELECT t.FQ_NAME, t.TABLE_SCHEMA, t.IS_TRANSIENT, t.RETENTION_TIME, t.CLONE_GROUP_ID, t.CREATED, t.TABLE_ID,
         date_diff('day', t.LAST_ALTERED, $as_of) AS DAYS_SINCE_ALTERED,
         coalesce(s.ACTIVE_BYTES, 0) AS ACTIVE_BYTES, coalesce(s.TIME_TRAVEL_BYTES, 0) AS TIME_TRAVEL_BYTES,
         coalesce(s.FAILSAFE_BYTES, 0) AS FAILSAFE_BYTES, coalesce(s.RETAINED_FOR_CLONE_BYTES, 0) AS RETAINED_FOR_CLONE_BYTES
  FROM TABLES t LEFT JOIN TABLE_STORAGE_METRICS s ON s.FQ_NAME = t.FQ_NAME),
grp AS (SELECT CLONE_GROUP_ID, count(*) AS MEMBERS, min(CREATED) AS FIRST_CREATED FROM TABLES GROUP BY CLONE_GROUP_ID),
r AS (SELECT OBJECT_NAME, count(*) AS READS FROM ACCESS_HISTORY WHERE ACCESS_TYPE = 'READ' GROUP BY OBJECT_NAME)
SELECT m.FQ_NAME AS OBJECT_NAME, 'staging_retention' AS CLUSTER_KEY, m.IS_TRANSIENT, m.RETENTION_TIME,
       m.DAYS_SINCE_ALTERED, coalesce(r.READS, 0) AS READS,
       m.TIME_TRAVEL_BYTES + m.FAILSAFE_BYTES AS WASTED_BYTES,
       (m.TIME_TRAVEL_BYTES + m.FAILSAFE_BYTES) / $bytes_per_tb AS WASTED_TB
FROM m LEFT JOIN r ON r.OBJECT_NAME = m.FQ_NAME
WHERE regexp_matches(m.TABLE_SCHEMA, $staging_schema_pattern)
UNION ALL
SELECT m.FQ_NAME, 'stale_clone', m.IS_TRANSIENT, m.RETENTION_TIME, m.DAYS_SINCE_ALTERED, coalesce(r.READS, 0),
       m.ACTIVE_BYTES + m.TIME_TRAVEL_BYTES + m.FAILSAFE_BYTES + m.RETAINED_FOR_CLONE_BYTES,
       (m.ACTIVE_BYTES + m.TIME_TRAVEL_BYTES + m.FAILSAFE_BYTES + m.RETAINED_FOR_CLONE_BYTES) / $bytes_per_tb
FROM m JOIN grp g ON g.CLONE_GROUP_ID = m.CLONE_GROUP_ID AND g.MEMBERS > 1 AND m.CREATED > g.FIRST_CREATED
LEFT JOIN r ON r.OBJECT_NAME = m.FQ_NAME
)
SELECT *, coalesce((WASTED_BYTES >= $min_wasted_bytes AND (
  (CLUSTER_KEY = 'staging_retention' AND (NOT IS_TRANSIENT OR RETENTION_TIME > $staging_max_retention_days))
  OR (CLUSTER_KEY = 'stale_clone' AND DAYS_SINCE_ALTERED >= $stale_clone_days AND READS = 0))), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
