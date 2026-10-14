-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COST-005 (14.5 cost, low): Stale clone retaining storage
-- threshold: rubric.foundation.stale_clone_retained_gb_max; playbook: PB-COST-STORAGE; autonomy: L2
SELECT FQ_NAME AS OBJECT_NAME, round(RETAINED_FOR_CLONE_BYTES / pow(1024, 3), 1) AS OBSERVED
FROM TABLE_STORAGE_METRICS WHERE NOT DELETED AND RETAINED_FOR_CLONE_BYTES / pow(1024, 3) > $threshold ORDER BY 1;
