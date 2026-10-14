-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-NET-002 (14.3 network, medium): Service user without a network policy
-- threshold: n/a; playbook: PB-NET-POLICY; autonomy: L2
SELECT NAME AS OBJECT_NAME, TYPE AS DETAIL FROM USERS
WHERE TYPE <> 'PERSON' AND NETWORK_POLICY IS NULL AND NOT DISABLED ORDER BY 1;
