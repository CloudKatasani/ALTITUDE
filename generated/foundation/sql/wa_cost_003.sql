-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COST-003 (14.5 cost, medium): Warehouse without a cost-centre tag
-- threshold: n/a; playbook: PB-COST-TAGGING; autonomy: L2
SELECT w.WAREHOUSE_NAME AS OBJECT_NAME, 'untagged spend' AS DETAIL FROM WAREHOUSES w
WHERE NOT EXISTS (SELECT 1 FROM TAG_REFERENCES t WHERE t.DOMAIN = 'WAREHOUSE' AND t.TAG_NAME = 'COST_CENTER'
                  AND t.OBJECT_NAME = w.WAREHOUSE_NAME)
ORDER BY 1;
