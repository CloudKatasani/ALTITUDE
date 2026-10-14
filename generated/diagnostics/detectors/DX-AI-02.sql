-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/diagnostics/checks/ai.yaml. Regenerate with `altitude generate`.
-- DX-AI-02: Cortex usage without budgets or dedicated roles
-- Domain D9 · WAF pillar cost_optimization · severity medium · last verified 2026-10-01
-- Source tables: CORTEX_USAGE_HISTORY, BUDGETS, USERS
-- Rubric: diagnostics@1.0.0:ab0816fc4c
-- Parameters (bound at run time; thresholds come from the rubric, never literals):
--   $budget_headroom = 0.25  (rubric.diagnostics.checks.ai_02.budget_headroom)
--   $days_per_month = <bound by the engine from the snapshot / rubric units>
--   $max_personal_usage_share = 0.2  (rubric.diagnostics.checks.ai_02.max_personal_usage_share)
--   $window_days = <bound by the engine from the snapshot / rubric units>
WITH __signals AS (
WITH u AS (
  SELECT c.*, coalesce(us.TYPE, 'PERSON') AS USER_TYPE
  FROM CORTEX_USAGE_HISTORY c LEFT JOIN USERS us ON us.NAME = c.USER_NAME)
SELECT 'CORTEX' AS OBJECT_NAME, 'ai_governance' AS CLUSTER_KEY,
       coalesce(sum(TOKEN_CREDITS), 0) AS CREDITS,
       count(*) AS CALLS,
       coalesce(avg(CASE WHEN USER_TYPE = 'PERSON' THEN 1 ELSE 0 END), 0) AS PERSONAL_USAGE_SHARE,
       coalesce(avg(CASE WHEN AGENT_NAME IS NULL THEN 1 ELSE 0 END), 0) AS NON_AGENT_SHARE,
       string_agg(DISTINCT ROLE_NAME, ', ' ORDER BY ROLE_NAME) AS ROLES,
       (SELECT count(*) FROM BUDGETS b WHERE upper(b.SCOPE) LIKE '%CORTEX%' OR upper(b.SCOPE) LIKE '%AI%') AS CORTEX_BUDGETS,
       coalesce(sum(TOKEN_CREDITS), 0) / $window_days * $days_per_month * (1 + $budget_headroom) AS SUGGESTED_MONTHLY_LIMIT
FROM u
)
SELECT *, coalesce((CREDITS > 0 AND (CORTEX_BUDGETS = 0 OR PERSONAL_USAGE_SHARE > $max_personal_usage_share)), false) AS FLAGGED
FROM __signals
ORDER BY OBJECT_NAME, CLUSTER_KEY;
