-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-003 (14.4 compute, medium): Warehouse auto-suspend exceeds policy
-- threshold: rubric.compute.auto_suspend_max_seconds; playbook: PB-COMP-AUTOSUSPEND; autonomy: L2
SELECT WAREHOUSE_NAME AS OBJECT_NAME, AUTO_SUSPEND AS OBSERVED FROM WAREHOUSES
WHERE AUTO_SUSPEND IS NULL OR AUTO_SUSPEND = 0 OR AUTO_SUSPEND > $threshold ORDER BY 1;
