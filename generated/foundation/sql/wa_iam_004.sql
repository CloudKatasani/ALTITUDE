-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-IAM-004 (14.2 identity, medium): Dormant user still enabled
-- threshold: rubric.foundation.dormant_user_days; playbook: PB-IAM-ACCESS-REVIEW; autonomy: L2
SELECT NAME AS OBJECT_NAME, date_diff('day', LAST_SUCCESS_LOGIN, CAST($as_of AS TIMESTAMP)) AS OBSERVED FROM USERS
WHERE NOT DISABLED AND (LAST_SUCCESS_LOGIN IS NULL
      OR LAST_SUCCESS_LOGIN < CAST($as_of AS TIMESTAMP) - to_days(CAST($threshold AS INTEGER)))
ORDER BY 1;
