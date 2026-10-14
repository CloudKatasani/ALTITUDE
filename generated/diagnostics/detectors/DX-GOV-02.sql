-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/gov.yaml. Regenerate with `altitude generate`.
-- DX-GOV-02: Tier-1 tables without data-quality monitoring
-- Domain D5 · WAF pillar security_governance · severity medium · last verified 2026-10-01
-- Source tables: TABLES, DATA_METRIC_FUNCTION_REFERENCES, COLUMNS, CLIENT_INPUTS, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
SELECT t.FQ_NAME AS OBJECT_NAME, t.FQ_NAME AS CLUSTER_KEY,
       (SELECT count(*) FROM DATA_METRIC_FUNCTION_REFERENCES d
        WHERE d.REF_ENTITY_NAME = t.FQ_NAME AND coalesce(d.SCHEDULE_STATUS, 'STARTED') = 'STARTED') AS DMF_COUNT,
       (SELECT c.COLUMN_NAME FROM COLUMNS c WHERE c.FQ_NAME = t.FQ_NAME ORDER BY c.ORDINAL_POSITION LIMIT 1) AS KEY_COLUMN
FROM TABLES t JOIN _TIER1_TABLES tt ON tt.FQ_NAME = t.FQ_NAME
)
SELECT *, coalesce((DMF_COUNT = 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
