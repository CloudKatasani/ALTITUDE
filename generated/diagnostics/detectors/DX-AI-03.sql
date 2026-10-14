-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/ai.yaml. Regenerate with `altitude generate`.
-- DX-AI-03: Low Tier-1 column comment coverage
-- Domain D9 · WAF pillar security_governance · severity low · last verified 2026-10-01
-- Source tables: COLUMNS, CLIENT_INPUTS, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $min_comment_coverage = 0.8  (rubric.diagnostics.checks.ai_03.min_comment_coverage)
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
SELECT c.FQ_NAME AS OBJECT_NAME, c.FQ_NAME AS CLUSTER_KEY,
       count(*) AS COLUMNS_TOTAL,
       count(*) FILTER (WHERE c.COMMENT IS NOT NULL AND trim(c.COMMENT) <> '') AS COLUMNS_COMMENTED,
       count(*) FILTER (WHERE c.COMMENT IS NOT NULL AND trim(c.COMMENT) <> '') / count(*) AS COMMENT_COVERAGE,
       string_agg(c.COLUMN_NAME, ',' ORDER BY c.ORDINAL_POSITION) FILTER (WHERE c.COMMENT IS NULL OR trim(c.COMMENT) = '') AS UNCOMMENTED_COLUMNS
FROM COLUMNS c JOIN _TIER1_TABLES tt ON tt.FQ_NAME = c.FQ_NAME
GROUP BY c.FQ_NAME
)
SELECT *, coalesce((COMMENT_COVERAGE < $min_comment_coverage), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
