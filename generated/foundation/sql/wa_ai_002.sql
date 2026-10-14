-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-AI-002 (14.8 ai, medium): Top KPI domain without a semantic view
-- threshold: n/a; playbook: PB-AI-SEMANTIC-VIEWS; autonomy: L2
WITH d AS (SELECT unnest(from_json("VALUE", '["VARCHAR"]')) AS DOMAIN FROM CLIENT_INPUTS WHERE "KEY" = 'top_kpi_domains')
SELECT DOMAIN AS OBJECT_NAME, 'no semantic view' AS DETAIL FROM d
WHERE NOT EXISTS (SELECT 1 FROM SEMANTIC_VIEWS s WHERE lower(s.KPI_DOMAIN) = lower(d.DOMAIN)) ORDER BY 1;
