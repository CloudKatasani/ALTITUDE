-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/ops.yaml. Regenerate with `altitude generate`.
-- DX-OPS-02: No alerting for credit spikes or failed Tier-1 tasks
-- Domain D6 · WAF pillar operational_excellence · severity high · last verified 2026-10-01
-- Source tables: ALERTS, RESOURCE_MONITORS, WAREHOUSES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $required_alert_classes = ["credit_anomaly", "task_failure"]  (value)
WITH __signals AS (
WITH req AS (SELECT unnest($required_alert_classes) AS ALERT_CLASS),
have AS (SELECT DISTINCT ALERT_CLASS FROM ALERTS WHERE lower(coalesce(STATE, 'started')) = 'started')
SELECT 'ACCOUNT' AS OBJECT_NAME, 'alerting' AS CLUSTER_KEY,
       (SELECT count(*) FROM req WHERE ALERT_CLASS NOT IN (SELECT ALERT_CLASS FROM have)) AS MISSING_ALERT_CLASSES,
       (SELECT string_agg(ALERT_CLASS, ',' ORDER BY ALERT_CLASS) FROM req WHERE ALERT_CLASS NOT IN (SELECT ALERT_CLASS FROM have)) AS MISSING_LIST,
       (SELECT count(*) FROM RESOURCE_MONITORS WHERE upper(LEVEL) = 'ACCOUNT') AS ACCOUNT_MONITORS,
       (SELECT count(*) FROM WAREHOUSES WHERE RESOURCE_MONITOR IS NULL) AS UNMONITORED_WAREHOUSES,
       (SELECT count(*) FROM WAREHOUSES) AS WAREHOUSES
)
SELECT *, coalesce((MISSING_ALERT_CLASSES > 0 OR ACCOUNT_MONITORS = 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
