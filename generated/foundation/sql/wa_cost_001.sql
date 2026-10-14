-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COST-001 (14.5 cost, high): Warehouse without a resource monitor
-- threshold: n/a; playbook: PB-COST-MONITORS; autonomy: L2
SELECT WAREHOUSE_NAME AS OBJECT_NAME, 'no resource monitor' AS DETAIL FROM WAREHOUSES
WHERE RESOURCE_MONITOR IS NULL ORDER BY 1;
