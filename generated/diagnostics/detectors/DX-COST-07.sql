-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/cost.yaml. Regenerate with `altitude generate`.
-- DX-COST-07: Untagged spend
-- Domain D1 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: WAREHOUSES, WAREHOUSE_METERING_HISTORY, QUERY_ATTRIBUTION_HISTORY, TAG_REFERENCES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $default_cost_center_tag = "COST_CENTER"  (value)
-- Helper _WAREHOUSE_CREDITS (HLP-WH-CREDITS): Billed vs query-attributed compute credits per warehouse over the snapshot window.
WITH __signals AS (
WITH tagname AS (
  SELECT upper(coalesce((SELECT VALUE ->> '$' FROM CLIENT_INPUTS WHERE KEY = 'cost_center_tag'), $default_cost_center_tag)) AS TAG),
tagged AS (
  SELECT DISTINCT OBJECT_NAME, TAG_DATABASE || '.' || TAG_SCHEMA || '.' || TAG_NAME AS TAG_FQ
  FROM TAG_REFERENCES, tagname WHERE DOMAIN = 'WAREHOUSE' AND upper(TAG_NAME) = tagname.TAG),
tot AS (SELECT sum(TOTAL_CREDITS) AS ALL_CREDITS FROM _WAREHOUSE_CREDITS)
SELECT w.WAREHOUSE_NAME AS OBJECT_NAME, 'cost_center' AS CLUSTER_KEY,
       c.TOTAL_CREDITS AS CREDITS,
       CASE WHEN tot.ALL_CREDITS > 0 THEN c.TOTAL_CREDITS / tot.ALL_CREDITS ELSE 0 END AS SPEND_SHARE,
       CASE WHEN t.OBJECT_NAME IS NULL THEN 0 ELSE 1 END AS HAS_COST_CENTER,
       coalesce((SELECT min(TAG_FQ) FROM tagged), 'GOVERNANCE.TAGS.' || (SELECT TAG FROM tagname)) AS TAG_FQ
FROM WAREHOUSES w
JOIN _WAREHOUSE_CREDITS c ON c.WAREHOUSE_NAME = w.WAREHOUSE_NAME
CROSS JOIN tot
LEFT JOIN tagged t ON t.OBJECT_NAME = w.WAREHOUSE_NAME
)
SELECT *, coalesce((HAS_COST_CENTER = 0 AND CREDITS > 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
