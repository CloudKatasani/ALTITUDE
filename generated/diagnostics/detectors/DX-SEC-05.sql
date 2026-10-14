-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/sec.yaml. Regenerate with `altitude generate`.
-- DX-SEC-05: Sensitive columns without masking
-- Domain D4 · WAF pillar security_governance · severity critical · last verified 2026-10-01
-- Source tables: TAG_REFERENCES, POLICY_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $sensitive_tags = ["PII", "SENSITIVE", "PHI", "PCI", "CONFIDENTIAL"]  (value)
WITH __signals AS (
WITH pii AS (
  SELECT OBJECT_DATABASE || '.' || OBJECT_SCHEMA || '.' || OBJECT_NAME AS TABLE_FQ, COLUMN_NAME,
         TAG_DATABASE || '.' || TAG_SCHEMA || '.' || TAG_NAME AS TAG_FQ, TAG_NAME, TAG_VALUE
  FROM TAG_REFERENCES WHERE DOMAIN = 'COLUMN' AND list_contains($sensitive_tags, upper(TAG_NAME))),
col_masked AS (
  SELECT REF_DATABASE_NAME || '.' || REF_SCHEMA_NAME || '.' || REF_ENTITY_NAME AS TABLE_FQ, REF_COLUMN_NAME
  FROM POLICY_REFERENCES WHERE POLICY_KIND = 'MASKING_POLICY' AND coalesce(POLICY_STATUS, 'ACTIVE') = 'ACTIVE'),
tag_masked AS (
  SELECT DISTINCT upper(TAG_NAME) AS TAG_NAME FROM POLICY_REFERENCES
  WHERE POLICY_KIND = 'MASKING_POLICY' AND TAG_NAME IS NOT NULL)
SELECT pii.TABLE_FQ || '.' || pii.COLUMN_NAME AS OBJECT_NAME, pii.TABLE_FQ AS CLUSTER_KEY,
       pii.TAG_FQ, pii.TAG_VALUE,
       CASE WHEN cm.REF_COLUMN_NAME IS NOT NULL OR tm.TAG_NAME IS NOT NULL THEN 1 ELSE 0 END AS IS_MASKED
FROM pii
LEFT JOIN col_masked cm ON cm.TABLE_FQ = pii.TABLE_FQ AND cm.REF_COLUMN_NAME = pii.COLUMN_NAME
LEFT JOIN tag_masked tm ON tm.TAG_NAME = upper(pii.TAG_NAME)
)
SELECT *, coalesce((IS_MASKED = 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
