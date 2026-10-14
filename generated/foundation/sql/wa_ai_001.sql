-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-AI-001 (14.8 ai, medium): Tier-1 column comment coverage below policy
-- threshold: rubric.foundation.tier1_column_comment_coverage_min; playbook: PB-AI-DOCUMENTATION; autonomy: L2
WITH t1 AS (SELECT unnest(from_json("VALUE", '["VARCHAR"]')) AS FQ FROM CLIENT_INPUTS WHERE "KEY" = 'tier1_tables')
SELECT c.FQ_NAME AS OBJECT_NAME, round(avg(CASE WHEN c.COMMENT IS NOT NULL THEN 1.0 ELSE 0.0 END), 3) AS OBSERVED
FROM COLUMNS c JOIN t1 ON t1.FQ = c.FQ_NAME GROUP BY 1
HAVING avg(CASE WHEN c.COMMENT IS NOT NULL THEN 1.0 ELSE 0.0 END) < $threshold ORDER BY 1;
