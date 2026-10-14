-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COST-002 (14.5 cost, medium): No account-level resource monitor
-- threshold: n/a; playbook: PB-COST-MONITORS; autonomy: L2
SELECT ACCOUNT_NAME AS OBJECT_NAME, 'no ACCOUNT-level monitor' AS DETAIL FROM ACCOUNT_INFO
WHERE NOT EXISTS (SELECT 1 FROM RESOURCE_MONITORS WHERE LEVEL = 'ACCOUNT') ORDER BY 1;
