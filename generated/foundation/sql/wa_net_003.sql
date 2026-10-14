-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-NET-003 (14.3 network, critical): Classified (PII-tagged) column without masking
-- threshold: n/a; playbook: PB-NET-TAG-MASKING; autonomy: L2
SELECT t.OBJECT_DATABASE || '.' || t.OBJECT_SCHEMA || '.' || t.OBJECT_NAME || '.' || t.COLUMN_NAME AS OBJECT_NAME,
       t.TAG_VALUE AS DETAIL
FROM TAG_REFERENCES t
WHERE t.TAG_NAME = 'PII' AND t.DOMAIN = 'COLUMN'
  AND NOT EXISTS (SELECT 1 FROM POLICY_REFERENCES p WHERE p.POLICY_KIND = 'MASKING_POLICY'
                  AND p.REF_DATABASE_NAME = t.OBJECT_DATABASE AND p.REF_SCHEMA_NAME = t.OBJECT_SCHEMA
                  AND p.REF_ENTITY_NAME = t.OBJECT_NAME AND p.REF_COLUMN_NAME = t.COLUMN_NAME)
  AND NOT EXISTS (SELECT 1 FROM POLICY_REFERENCES p WHERE p.POLICY_KIND = 'MASKING_POLICY' AND p.TAG_NAME = 'PII')
ORDER BY 1;
