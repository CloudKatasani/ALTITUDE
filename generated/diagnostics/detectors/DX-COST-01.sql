-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-01: Idle-heavy warehouses
-- Domain D1 · WAF pillar cost_optimization · severity high · last verified 2026-10-01
-- Source tables: WAREHOUSES, WAREHOUSE_METERING_HISTORY, QUERY_ATTRIBUTION_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $auto_suspend_max_seconds = 60  (rubric.diagnostics.checks.cost_01.auto_suspend_max_seconds)
--   $idle_share_min = 0.6  (rubric.diagnostics.checks.cost_01.idle_share_min)
-- Helper _WAREHOUSE_CREDITS (HLP-WH-CREDITS): Billed vs query-attributed compute credits per warehouse over the snapshot window.
WITH __signals AS (
SELECT w.WAREHOUSE_NAME AS OBJECT_NAME,
       'auto_suspend' AS CLUSTER_KEY,
       w.WAREHOUSE_SIZE, w.WORKLOAD_CLASS, w.AUTO_SUSPEND,
       c.BILLED_CREDITS, c.ATTRIBUTED_CREDITS,
       greatest(c.BILLED_CREDITS - c.ATTRIBUTED_CREDITS, 0) AS IDLE_CREDITS,
       CASE WHEN c.BILLED_CREDITS > 0
            THEN greatest(c.BILLED_CREDITS - c.ATTRIBUTED_CREDITS, 0) / c.BILLED_CREDITS ELSE 0 END AS IDLE_SHARE
FROM WAREHOUSES w JOIN _WAREHOUSE_CREDITS c ON c.WAREHOUSE_NAME = w.WAREHOUSE_NAME
)
SELECT *, coalesce((IDLE_SHARE >= $idle_share_min AND AUTO_SUSPEND > $auto_suspend_max_seconds AND BILLED_CREDITS > 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
