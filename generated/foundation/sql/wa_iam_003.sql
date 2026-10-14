-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-IAM-003 (14.2 identity, high): ACCOUNTADMIN granted beyond the break-glass limit
-- threshold: rubric.foundation.accountadmin_max_holders; playbook: PB-IAM-BREAK-GLASS; autonomy: L2
WITH h AS (SELECT DISTINCT GRANTEE_NAME FROM GRANTS_TO_USERS WHERE ROLE = 'ACCOUNTADMIN')
SELECT GRANTEE_NAME AS OBJECT_NAME, (SELECT count(*) FROM h) AS OBSERVED FROM h
WHERE (SELECT count(*) FROM h) > $threshold ORDER BY 1;
