-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/compute_cost.yaml. Regenerate with `altitude generate`.
-- WA-COMP-005 (14.4 compute, medium): Statement timeout missing or above policy
-- threshold: rubric.compute.statement_timeout_max_seconds; playbook: PB-COMP-TIMEOUTS; autonomy: L2
SELECT WAREHOUSE_NAME AS OBJECT_NAME, STATEMENT_TIMEOUT_IN_SECONDS AS OBSERVED FROM WAREHOUSES
WHERE STATEMENT_TIMEOUT_IN_SECONDS IS NULL OR STATEMENT_TIMEOUT_IN_SECONDS > $threshold ORDER BY 1;
