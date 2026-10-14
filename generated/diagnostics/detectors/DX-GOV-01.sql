-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/gov.yaml. Regenerate with `altitude generate`.
-- DX-GOV-01: Tier-1 objects without owner or description
-- Domain D5 · WAF pillar security_governance · severity medium · last verified 2026-10-01
-- Source tables: TABLES, TAG_REFERENCES, ACCESS_HISTORY, CLIENT_INPUTS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $default_owner_tag = "DATA_OWNER"  (value)
-- Helper _TIER1_TABLES (HLP-TIER1): Tier-1 tables from the engagement intake (CLIENT_INPUTS.tier1_tables) or a TIER=tier1 tag.
WITH __signals AS (
WITH tagname AS (
  SELECT upper(coalesce((SELECT VALUE ->> '$' FROM CLIENT_INPUTS WHERE KEY = 'owner_tag'), $default_owner_tag)) AS TAG),
owners AS (
  SELECT OBJECT_DATABASE || '.' || OBJECT_SCHEMA || '.' || OBJECT_NAME AS FQ_NAME,
         TAG_DATABASE || '.' || TAG_SCHEMA || '.' || TAG_NAME AS TAG_FQ, TAG_VALUE
  FROM TAG_REFERENCES, tagname WHERE DOMAIN = 'TABLE' AND upper(TAG_NAME) = tagname.TAG),
writers AS (
  SELECT OBJECT_NAME, USER_NAME, count(*) AS N,
         row_number() OVER (PARTITION BY OBJECT_NAME ORDER BY count(*) DESC, USER_NAME) AS RN
  FROM ACCESS_HISTORY WHERE ACCESS_TYPE = 'WRITE' GROUP BY OBJECT_NAME, USER_NAME)
SELECT t.FQ_NAME AS OBJECT_NAME,
       coalesce(w.USER_NAME, t.TABLE_OWNER) AS CLUSTER_KEY,
       CASE WHEN o.TAG_VALUE IS NULL THEN 0 ELSE 1 END AS HAS_OWNER_TAG,
       CASE WHEN t.COMMENT IS NULL OR trim(t.COMMENT) = '' THEN 0 ELSE 1 END AS HAS_COMMENT,
       coalesce(w.USER_NAME, t.TABLE_OWNER) AS SUGGESTED_OWNER,
       coalesce((SELECT min(TAG_FQ) FROM owners), 'GOVERNANCE.TAGS.' || (SELECT TAG FROM tagname)) AS OWNER_TAG_FQ
FROM TABLES t
JOIN _TIER1_TABLES tt ON tt.FQ_NAME = t.FQ_NAME
LEFT JOIN owners o ON o.FQ_NAME = t.FQ_NAME
LEFT JOIN writers w ON w.OBJECT_NAME = t.FQ_NAME AND w.RN = 1
)
SELECT *, coalesce((HAS_OWNER_TAG = 0 OR HAS_COMMENT = 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
