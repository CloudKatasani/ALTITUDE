-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/rel.yaml. Regenerate with `altitude generate`.
-- DX-REL-02: Freshness SLA misses on Tier-1 tables
-- Domain D3 · WAF pillar reliability · severity high · last verified 2026-10-01
-- Source tables: TASK_HISTORY, CLIENT_INPUTS, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $max_miss_rate = 0.05  (rubric.diagnostics.checks.rel_02.max_miss_rate)
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
WITH sla AS (
  SELECT unnest(from_json(VALUE, '[{"table":"VARCHAR","loaded_by":"VARCHAR","deadline_utc":"VARCHAR"}]'), recursive := true)
  FROM CLIENT_INPUTS WHERE KEY = 'freshness_slas'),
days AS (
  SELECT DISTINCT CAST(SCHEDULED_TIME AS DATE) AS D FROM TASK_HISTORY),
done AS (
  SELECT FQ_NAME, CAST(COMPLETED_TIME AS DATE) AS D, min(COMPLETED_TIME) AS FIRST_SUCCESS
  FROM TASK_HISTORY WHERE STATE = 'SUCCEEDED' GROUP BY FQ_NAME, CAST(COMPLETED_TIME AS DATE)),
daily AS (
  SELECT sla."table" AS TABLE_NAME, sla.loaded_by AS LOADED_BY, sla.deadline_utc AS DEADLINE_UTC, days.D,
         CASE WHEN done.FIRST_SUCCESS IS NULL
                OR CAST(done.FIRST_SUCCESS AS TIME) > CAST(sla.deadline_utc AS TIME) THEN 1 ELSE 0 END AS MISSED,
         date_diff('minute', days.D + CAST(sla.deadline_utc AS TIME), done.FIRST_SUCCESS) AS LATE_MINUTES
  FROM sla CROSS JOIN days
  LEFT JOIN done ON done.FQ_NAME = sla.loaded_by AND done.D = days.D)
SELECT TABLE_NAME AS OBJECT_NAME, LOADED_BY AS CLUSTER_KEY, LOADED_BY, DEADLINE_UTC,
       count(*) AS SLA_DAYS, sum(MISSED) AS MISSED_DAYS, sum(MISSED) / count(*) AS MISS_RATE,
       coalesce(max(LATE_MINUTES) FILTER (WHERE MISSED = 1), 0) AS MAX_LATE_MINUTES,
       CASE WHEN TABLE_NAME IN (SELECT FQ_NAME FROM _TIER1_TABLES) THEN 1 ELSE 0 END AS IS_TIER1
FROM daily GROUP BY TABLE_NAME, LOADED_BY, DEADLINE_UTC
)
SELECT *, coalesce((IS_TIER1 = 1 AND MISS_RATE >= $max_miss_rate), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
