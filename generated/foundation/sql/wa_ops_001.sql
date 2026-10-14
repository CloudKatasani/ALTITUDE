-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-OPS-001 (14.7 observability, high): No alert for failed tasks
-- threshold: n/a; playbook: PB-OPS-ALERT-PACK; autonomy: L2
SELECT ACCOUNT_NAME AS OBJECT_NAME, 'task_failure' AS DETAIL FROM ACCOUNT_INFO
WHERE NOT EXISTS (SELECT 1 FROM ALERTS WHERE ALERT_CLASS = 'task_failure' AND STATE = 'started');
