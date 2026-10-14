-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-IAM-001 (14.2 identity, critical): Human user signs in with a password and no MFA or SSO
-- threshold: n/a; playbook: PB-IAM-MFA; autonomy: L2
SELECT NAME AS OBJECT_NAME, 'password, no MFA, no SSO' AS DETAIL FROM USERS
WHERE TYPE = 'PERSON' AND HAS_PASSWORD AND NOT HAS_MFA AND EXT_AUTHN_UID IS NULL AND NOT DISABLED
ORDER BY 1;
