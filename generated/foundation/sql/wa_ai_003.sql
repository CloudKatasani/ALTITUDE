-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-AI-003 (14.8 ai, medium): Cortex usage without a budget
-- threshold: n/a; playbook: PB-AI-AGENT-CONTROLS; autonomy: L2
SELECT 'CORTEX' AS OBJECT_NAME, round(sum(TOKEN_CREDITS), 2) AS OBSERVED FROM CORTEX_USAGE_HISTORY
HAVING count(*) > 0 AND NOT EXISTS (SELECT 1 FROM BUDGETS WHERE SCOPE = 'CORTEX');
