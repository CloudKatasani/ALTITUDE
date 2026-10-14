-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-ENG-003 (14.6 engineering, high): Pipeline runs under a personal user
-- threshold: rubric.foundation.personal_pipeline_min_days; playbook: PB-ENG-SERVICE-IDENTITY; autonomy: L1
SELECT q.USER_NAME AS OBJECT_NAME, count(DISTINCT CAST(q.START_TIME AS DATE)) AS OBSERVED FROM QUERY_HISTORY q
JOIN USERS u ON u.NAME = q.USER_NAME
WHERE u.TYPE = 'PERSON' AND q.QUERY_TYPE IN ('INSERT', 'MERGE', 'CREATE_TABLE_AS_SELECT', 'COPY', 'UPDATE', 'DELETE')
GROUP BY 1 HAVING count(DISTINCT CAST(q.START_TIME AS DATE)) >= $threshold ORDER BY 1;
