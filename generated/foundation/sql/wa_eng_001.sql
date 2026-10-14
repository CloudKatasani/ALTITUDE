-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-ENG-001 (14.6 engineering, medium): Tier-1 table without data metric functions
-- threshold: n/a; playbook: PB-ENG-DMF; autonomy: L2
WITH t1 AS (SELECT unnest(from_json("VALUE", '["VARCHAR"]')) AS FQ FROM CLIENT_INPUTS WHERE "KEY" = 'tier1_tables')
SELECT FQ AS OBJECT_NAME, 'no DMF attached' AS DETAIL FROM t1
WHERE NOT EXISTS (SELECT 1 FROM DATA_METRIC_FUNCTION_REFERENCES d WHERE d.REF_ENTITY_NAME = t1.FQ) ORDER BY 1;
