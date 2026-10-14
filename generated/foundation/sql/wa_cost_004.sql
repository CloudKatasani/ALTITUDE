-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COST-004 (14.5 cost, low): Staging table is permanent or keeps long Time Travel
-- threshold: rubric.foundation.staging_retention_max_days; playbook: PB-COST-STORAGE; autonomy: L2
SELECT FQ_NAME AS OBJECT_NAME, RETENTION_TIME AS OBSERVED FROM TABLES
WHERE upper(TABLE_SCHEMA) LIKE '%STAG%' AND (NOT IS_TRANSIENT OR RETENTION_TIME > $threshold) ORDER BY 1;
