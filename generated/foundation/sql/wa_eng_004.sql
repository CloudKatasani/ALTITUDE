-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-ENG-004 (14.6 engineering, medium): Tier-1 table without owner tag or description
-- threshold: n/a; playbook: PB-ENG-OWNERSHIP; autonomy: L2
WITH t1 AS (SELECT unnest(from_json("VALUE", '["VARCHAR"]')) AS FQ FROM CLIENT_INPUTS WHERE "KEY" = 'tier1_tables')
SELECT t.FQ_NAME AS OBJECT_NAME,
       CASE WHEN t.COMMENT IS NULL THEN 'no comment' ELSE 'no owner tag' END AS DETAIL
FROM TABLES t JOIN t1 ON t1.FQ = t.FQ_NAME
WHERE t.COMMENT IS NULL OR NOT EXISTS (
  SELECT 1 FROM TAG_REFERENCES r WHERE r.TAG_NAME = 'DATA_OWNER' AND r.DOMAIN = 'TABLE'
    AND r.OBJECT_DATABASE = t.TABLE_CATALOG AND r.OBJECT_SCHEMA = t.TABLE_SCHEMA AND r.OBJECT_NAME = t.TABLE_NAME)
ORDER BY 1;
