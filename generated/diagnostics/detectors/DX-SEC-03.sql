-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/sec.yaml. Regenerate with `altitude generate`.
-- DX-SEC-03: Dormant users and orphan roles
-- Domain D4 · WAF pillar security_governance · severity medium · last verified 2026-10-01
-- Source tables: USERS, ROLES, GRANTS_TO_USERS, GRANTS_TO_ROLES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $as_of = <bound by the engine from the snapshot / rubric units>
--   $dormant_days = 90  (rubric.diagnostics.checks.sec_03.dormant_days)
--   $system_roles = ["ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "USERADMIN", "ORGADMIN", "PUBLIC"]  (value)
WITH __signals AS (
SELECT u.NAME AS OBJECT_NAME, 'dormant_user' AS CLUSTER_KEY,
       date_diff('day', coalesce(u.LAST_SUCCESS_LOGIN, u.CREATED_ON), $as_of) AS DAYS_SINCE_LOGIN,
       NULL::BIGINT AS USER_GRANTS, NULL::BIGINT AS PARENT_ROLES, NULL::VARCHAR AS GRANTS_HELD
FROM USERS u WHERE NOT coalesce(u.DISABLED, false)
UNION ALL
SELECT r.NAME, 'orphan_role', NULL,
       (SELECT count(*) FROM GRANTS_TO_USERS gu WHERE gu.ROLE = r.NAME),
       (SELECT count(*) FROM GRANTS_TO_ROLES gr WHERE gr.GRANTED_ON = 'ROLE' AND gr.NAME = r.NAME),
       (SELECT string_agg(gr.PRIVILEGE || '|' || gr.GRANTED_ON || '|' ||
                coalesce(gr.TABLE_CATALOG || '.', '') || coalesce(gr.TABLE_SCHEMA || '.', '') || gr.NAME, ';'
                ORDER BY gr.PRIVILEGE, gr.NAME)
        FROM GRANTS_TO_ROLES gr WHERE gr.GRANTEE_NAME = r.NAME)
FROM ROLES r WHERE NOT list_contains($system_roles, r.NAME)
)
SELECT *, coalesce(((CLUSTER_KEY = 'dormant_user' AND DAYS_SINCE_LOGIN >= $dormant_days) OR (CLUSTER_KEY = 'orphan_role' AND USER_GRANTS = 0 AND PARENT_ROLES = 0)), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
