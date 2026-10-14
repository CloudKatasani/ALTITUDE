-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-IAM-002 (14.2 identity, high): Service user authenticates with a password
-- threshold: n/a; playbook: PB-IAM-SERVICE-KEYPAIR; autonomy: L1
SELECT NAME AS OBJECT_NAME, TYPE AS DETAIL FROM USERS
WHERE TYPE IN ('SERVICE', 'LEGACY_SERVICE') AND HAS_PASSWORD AND NOT DISABLED ORDER BY 1;
