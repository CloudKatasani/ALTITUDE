-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/ai.yaml. Regenerate with `altitude generate`.
-- DX-AI-01: No semantic views for top KPI domains
-- Domain D9 · WAF pillar operational_excellence · severity medium · last verified 2026-10-01
-- Source tables: SEMANTIC_VIEWS, CLIENT_INPUTS, TABLES, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
WITH d AS (SELECT unnest(from_json(VALUE, '["VARCHAR"]')) AS KPI_DOMAIN FROM CLIENT_INPUTS WHERE KEY = 'top_kpi_domains')
SELECT d.KPI_DOMAIN AS OBJECT_NAME, 'semantic_layer' AS CLUSTER_KEY,
       (SELECT count(*) FROM SEMANTIC_VIEWS s WHERE lower(s.KPI_DOMAIN) = lower(d.KPI_DOMAIN)) AS SEMANTIC_VIEWS,
       (SELECT string_agg(t.FQ_NAME, ',' ORDER BY t.FQ_NAME) FROM TABLES t JOIN _TIER1_TABLES tt ON tt.FQ_NAME = t.FQ_NAME
        WHERE upper(t.TABLE_SCHEMA) = upper(d.KPI_DOMAIN)) AS CANDIDATE_TABLES
FROM d
)
SELECT *, coalesce((SEMANTIC_VIEWS = 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
