-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/sec.yaml. Regenerate with `altitude generate`.
-- DX-SEC-02: ACCOUNTADMIN sprawl
-- Domain D4 · WAF pillar security_governance · severity critical · last verified 2026-10-01
-- Source tables: GRANTS_TO_USERS, QUERY_HISTORY, USERS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $max_accountadmin_grantees = 2  (rubric.diagnostics.checks.sec_02.max_accountadmin_grantees)
--   $max_accountadmin_usage_day_share = 0.1  (rubric.diagnostics.checks.sec_02.max_accountadmin_usage_day_share)
--   $window_days = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH g AS (
  SELECT gu.GRANTEE_NAME, u.HAS_MFA, CASE WHEN u.EXT_AUTHN_UID IS NOT NULL THEN 1 ELSE 0 END AS HAS_SSO, u.CREATED_ON
  FROM GRANTS_TO_USERS gu LEFT JOIN USERS u ON u.NAME = gu.GRANTEE_NAME
  WHERE gu.ROLE = 'ACCOUNTADMIN'),
ranked AS (
  SELECT *, row_number() OVER (ORDER BY HAS_SSO DESC, HAS_MFA DESC, CREATED_ON, GRANTEE_NAME) AS KEEP_RANK FROM g),
used AS (
  SELECT count(*) AS USAGE_QUERIES, count(DISTINCT CAST(START_TIME AS DATE)) AS USAGE_DAYS,
         count(DISTINCT USER_NAME) AS USAGE_USERS
  FROM QUERY_HISTORY WHERE ROLE_NAME = 'ACCOUNTADMIN')
SELECT 'ACCOUNTADMIN' AS OBJECT_NAME, 'break_glass' AS CLUSTER_KEY,
       (SELECT count(*) FROM g) AS GRANTEES,
       (SELECT string_agg(GRANTEE_NAME, ', ' ORDER BY GRANTEE_NAME) FROM g) AS GRANTEE_LIST,
       (SELECT string_agg(GRANTEE_NAME, ',' ORDER BY GRANTEE_NAME) FROM ranked WHERE KEEP_RANK > $max_accountadmin_grantees) AS REVOKE_CANDIDATES,
       used.USAGE_QUERIES, used.USAGE_DAYS, used.USAGE_USERS,
       used.USAGE_DAYS / $window_days AS USAGE_DAY_SHARE
FROM used
)
SELECT *, coalesce((GRANTEES > $max_accountadmin_grantees OR USAGE_DAY_SHARE > $max_accountadmin_usage_day_share), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
