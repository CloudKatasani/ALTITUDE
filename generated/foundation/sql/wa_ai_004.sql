-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-AI-004 (14.8 ai, medium): AI usage under human or functional roles instead of a dedicated agent role
-- threshold: n/a; playbook: PB-AI-AGENT-CONTROLS; autonomy: L2
SELECT ROLE_NAME AS OBJECT_NAME, count(*) AS OBSERVED FROM CORTEX_USAGE_HISTORY
WHERE AGENT_NAME IS NULL OR ROLE_NAME NOT LIKE '%AGENT%' GROUP BY 1 ORDER BY 1;
