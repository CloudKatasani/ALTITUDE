-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-IAM-005 (14.2 identity, low): Orphan role (granted to no user and no role)
-- threshold: n/a; playbook: PB-IAM-ACCESS-REVIEW; autonomy: L2
SELECT r.NAME AS OBJECT_NAME, 'no users, no parent role' AS DETAIL FROM ROLES r
WHERE r.NAME NOT IN ('ACCOUNTADMIN', 'SECURITYADMIN', 'SYSADMIN', 'USERADMIN', 'ORGADMIN', 'PUBLIC')
  AND NOT EXISTS (SELECT 1 FROM GRANTS_TO_USERS u WHERE u.ROLE = r.NAME)
  AND NOT EXISTS (SELECT 1 FROM GRANTS_TO_ROLES g WHERE g.GRANTED_ON = 'ROLE' AND g.NAME = r.NAME)
ORDER BY 1;
