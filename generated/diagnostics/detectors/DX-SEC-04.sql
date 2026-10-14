-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/sec.yaml. Regenerate with `altitude generate`.
-- DX-SEC-04: Missing network policy
-- Domain D4 · WAF pillar security_governance · severity high · last verified 2026-10-01
-- Source tables: ACCOUNT_INFO, USERS, LOGIN_HISTORY, NETWORK_POLICIES
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $service_user_types = ["SERVICE", "LEGACY_SERVICE"]  (value)
WITH __signals AS (
SELECT 'ACCOUNT' AS OBJECT_NAME, 'network_policy' AS CLUSTER_KEY,
       a.NETWORK_POLICY AS ACCOUNT_POLICY,
       CASE WHEN a.NETWORK_POLICY IS NULL THEN 0 ELSE 1 END AS HAS_ACCOUNT_POLICY,
       (SELECT count(*) FROM USERS u WHERE list_contains($service_user_types, u.TYPE) AND u.NETWORK_POLICY IS NULL) AS SERVICE_USERS_WITHOUT_POLICY,
       (SELECT string_agg(u.NAME, ', ' ORDER BY u.NAME) FROM USERS u
        WHERE list_contains($service_user_types, u.TYPE) AND u.NETWORK_POLICY IS NULL) AS SERVICE_USERS_LIST,
       (SELECT string_agg(DISTINCT regexp_extract(CLIENT_IP, '^([0-9]+\.[0-9]+)\.', 1) || '.0.0/16', ',' ORDER BY 1)
        FROM LOGIN_HISTORY WHERE IS_SUCCESS = 'YES' AND regexp_matches(CLIENT_IP, '^[0-9]+\.[0-9]+\.')) AS OBSERVED_CIDRS
FROM ACCOUNT_INFO a
)
SELECT *, coalesce((HAS_ACCOUNT_POLICY = 0 OR SERVICE_USERS_WITHOUT_POLICY > 0), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
