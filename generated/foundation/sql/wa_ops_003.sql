-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-OPS-003 (14.7 observability, medium): No alert on privileged-role use
-- threshold: n/a; playbook: PB-OPS-ALERT-PACK; autonomy: L2
SELECT ACCOUNT_NAME AS OBJECT_NAME, 'privileged_use' AS DETAIL FROM ACCOUNT_INFO
WHERE NOT EXISTS (SELECT 1 FROM ALERTS WHERE ALERT_CLASS = 'privileged_use' AND STATE = 'started');
