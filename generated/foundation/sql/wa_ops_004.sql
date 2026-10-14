-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-OPS-004 (14.7 observability, high): Task failure rate above policy
-- threshold: rubric.foundation.task_failure_ratio_max; playbook: PB-OPS-PIPELINE-TRIAGE; autonomy: L2
SELECT FQ_NAME AS OBJECT_NAME, round(avg(CASE WHEN STATE = 'FAILED' THEN 1.0 ELSE 0.0 END), 3) AS OBSERVED
FROM TASK_HISTORY WHERE STATE IN ('FAILED', 'SUCCEEDED') GROUP BY 1
HAVING avg(CASE WHEN STATE = 'FAILED' THEN 1.0 ELSE 0.0 END) > $threshold ORDER BY 1;
