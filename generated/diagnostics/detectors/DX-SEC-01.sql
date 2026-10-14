-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/sec.yaml. Regenerate with `altitude generate`.
-- DX-SEC-01: Weak authentication
-- Domain D4 · WAF pillar security_governance · severity critical · last verified 2026-10-01
-- Source tables: USERS, LOGIN_HISTORY
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $service_user_types = ["SERVICE", "LEGACY_SERVICE"]  (value)
WITH __signals AS (
WITH l AS (
  SELECT USER_NAME, count(*) AS LOGINS,
         count(*) FILTER (WHERE FIRST_AUTHENTICATION_FACTOR = 'PASSWORD' AND SECOND_AUTHENTICATION_FACTOR IS NULL) AS SINGLE_FACTOR_LOGINS
  FROM LOGIN_HISTORY WHERE IS_SUCCESS = 'YES' GROUP BY USER_NAME)
SELECT u.NAME AS OBJECT_NAME,
       CASE WHEN list_contains($service_user_types, coalesce(u.TYPE, 'PERSON')) THEN 'service_password' ELSE 'human_without_mfa' END AS CLUSTER_KEY,
       coalesce(u.TYPE, 'PERSON') AS USER_TYPE, u.HAS_PASSWORD, u.HAS_MFA, u.HAS_RSA_PUBLIC_KEY,
       CASE WHEN u.EXT_AUTHN_UID IS NOT NULL THEN 1 ELSE 0 END AS HAS_SSO,
       coalesce(l.LOGINS, 0) AS LOGINS, coalesce(l.SINGLE_FACTOR_LOGINS, 0) AS SINGLE_FACTOR_LOGINS
FROM USERS u LEFT JOIN l ON l.USER_NAME = u.NAME
WHERE NOT coalesce(u.DISABLED, false)
)
SELECT *, coalesce(((CLUSTER_KEY = 'human_without_mfa' AND HAS_PASSWORD AND NOT HAS_MFA AND HAS_SSO = 0) OR (CLUSTER_KEY = 'service_password' AND HAS_PASSWORD)), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
