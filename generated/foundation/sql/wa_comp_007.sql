-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-007 (14.4 compute, medium): Queries spill to remote storage
-- threshold: rubric.compute.remote_spill_max_gb; playbook: PB-COMP-SPILL; autonomy: L2
SELECT WAREHOUSE_NAME AS OBJECT_NAME, round(sum(BYTES_SPILLED_TO_REMOTE_STORAGE) / pow(1024, 3), 1) AS OBSERVED
FROM QUERY_HISTORY WHERE WAREHOUSE_NAME IS NOT NULL GROUP BY 1
HAVING sum(BYTES_SPILLED_TO_REMOTE_STORAGE) / pow(1024, 3) > $threshold ORDER BY 1;
