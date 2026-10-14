-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-OPS-002 (14.7 observability, medium): No alert for credit spikes
-- threshold: n/a; playbook: PB-OPS-ALERT-PACK; autonomy: L2
SELECT ACCOUNT_NAME AS OBJECT_NAME, 'credit_anomaly' AS DETAIL FROM ACCOUNT_INFO
WHERE NOT EXISTS (SELECT 1 FROM ALERTS WHERE ALERT_CLASS = 'credit_anomaly' AND STATE = 'started');
