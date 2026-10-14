-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/gov.yaml. Regenerate with `altitude generate`.
-- DX-GOV-03: Unused objects
-- Domain D5 · WAF pillar security_governance · severity low · last verified 2026-10-01
-- Source tables: TABLES, ACCESS_HISTORY, TABLE_STORAGE_METRICS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $as_of = <bound by the engine from the snapshot / rubric units>
--   $bytes_per_tb = <bound by the engine from the snapshot / rubric units>
--   $unused_days = 180  (rubric.diagnostics.checks.gov_03.unused_days)
WITH __signals AS (
WITH la AS (SELECT OBJECT_NAME, max(QUERY_START_TIME) AS LAST_ACCESS FROM ACCESS_HISTORY GROUP BY OBJECT_NAME)
SELECT t.FQ_NAME AS OBJECT_NAME, 'archive' AS CLUSTER_KEY, t.TABLE_CATALOG, t.TABLE_NAME,
       date_diff('day', t.LAST_ALTERED, $as_of) AS DAYS_SINCE_ALTERED,
       la.LAST_ACCESS,
       CASE WHEN la.LAST_ACCESS IS NULL THEN 1 ELSE 0 END AS NO_ACCESS_IN_WINDOW,
       coalesce(s.ACTIVE_BYTES, 0) + coalesce(s.TIME_TRAVEL_BYTES, 0) + coalesce(s.FAILSAFE_BYTES, 0) AS STORAGE_BYTES,
       (coalesce(s.ACTIVE_BYTES, 0) + coalesce(s.TIME_TRAVEL_BYTES, 0) + coalesce(s.FAILSAFE_BYTES, 0)) / $bytes_per_tb AS STORAGE_TB
FROM TABLES t
LEFT JOIN la ON la.OBJECT_NAME = t.FQ_NAME
LEFT JOIN TABLE_STORAGE_METRICS s ON s.FQ_NAME = t.FQ_NAME
)
SELECT *, coalesce((NO_ACCESS_IN_WINDOW = 1 AND DAYS_SINCE_ALTERED >= $unused_days), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
