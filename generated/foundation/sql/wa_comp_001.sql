-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-001 (14.4 compute, low): Warehouse not assigned to a known workload class
-- threshold: n/a; playbook: PB-COMP-WORKLOAD-CLASS; autonomy: L1
SELECT WAREHOUSE_NAME AS OBJECT_NAME, coalesce(WORKLOAD_CLASS, '(none)') AS DETAIL FROM WAREHOUSES
WHERE WORKLOAD_CLASS IS NULL OR NOT list_contains($classes, WORKLOAD_CLASS) ORDER BY 1;
