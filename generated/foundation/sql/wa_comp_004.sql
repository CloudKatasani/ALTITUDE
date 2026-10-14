-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-004 (14.4 compute, low): Warehouse auto-resume disabled
-- threshold: n/a; playbook: PB-COMP-AUTOSUSPEND; autonomy: L2
SELECT WAREHOUSE_NAME AS OBJECT_NAME, 'AUTO_RESUME = FALSE' AS DETAIL FROM WAREHOUSES WHERE NOT AUTO_RESUME ORDER BY 1;
