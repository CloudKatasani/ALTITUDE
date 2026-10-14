-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/rel.yaml. Regenerate with `altitude generate`.
-- DX-REL-04: Tier-1 data without replication or failover
-- Domain D3 · WAF pillar reliability · severity critical · last verified 2026-10-01
-- Source tables: REPLICATION_GROUPS, CLIENT_INPUTS, ACCOUNT_INFO
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $max_rpo_hours_requiring_dr = 24  (rubric.diagnostics.checks.rel_04.max_rpo_hours_requiring_dr)
--   $minutes_per_hour = <bound by the engine from the snapshot / rubric units>
--   $schedule_share_of_rpo = 0.5  (rubric.diagnostics.checks.rel_04.schedule_share_of_rpo)
WITH __signals AS (
WITH rpo AS (
  SELECT k AS DATABASE_NAME, CAST(json_extract_string(VALUE, '$."' || k || '"') AS DOUBLE) AS RPO_HOURS
  FROM CLIENT_INPUTS, unnest(json_keys(VALUE)) AS t(k) WHERE KEY = 'rpo_hours'),
rep AS (
  SELECT trim(d.DB) AS DATABASE_NAME, g.NAME,
         CAST(regexp_extract(g.REPLICATION_SCHEDULE, '([0-9]+)\s*MINUTE', 1) AS DOUBLE) / $minutes_per_hour AS SCHEDULE_HOURS
  FROM REPLICATION_GROUPS g, unnest(string_split(g.ALLOWED_DATABASES, ',')) AS d(DB))
SELECT rpo.DATABASE_NAME AS OBJECT_NAME, rpo.DATABASE_NAME AS CLUSTER_KEY, rpo.RPO_HOURS,
       count(rep.NAME) AS REPLICATION_GROUPS, min(rep.SCHEDULE_HOURS) AS SCHEDULE_HOURS,
       rpo.RPO_HOURS * $minutes_per_hour * $schedule_share_of_rpo AS TARGET_SCHEDULE_MINUTES,
       (SELECT min(ORGANIZATION_NAME) FROM ACCOUNT_INFO) AS ORGANIZATION_NAME,
       (SELECT min(ACCOUNT_NAME) FROM ACCOUNT_INFO) AS ACCOUNT_NAME
FROM rpo LEFT JOIN rep ON rep.DATABASE_NAME = rpo.DATABASE_NAME
GROUP BY rpo.DATABASE_NAME, rpo.RPO_HOURS
)
SELECT *, coalesce((RPO_HOURS <= $max_rpo_hours_requiring_dr AND (REPLICATION_GROUPS = 0 OR SCHEDULE_HOURS > RPO_HOURS)), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
