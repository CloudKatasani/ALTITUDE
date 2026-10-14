-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-NET-001 (14.3 network, high): Account has no network policy
-- threshold: n/a; playbook: PB-NET-POLICY; autonomy: L2
SELECT ACCOUNT_NAME AS OBJECT_NAME, 'no account-level network policy' AS DETAIL FROM ACCOUNT_INFO
WHERE NETWORK_POLICY IS NULL ORDER BY 1;
