-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/operations_ai.yaml. Regenerate with `altitude generate`.
-- WA-ENG-002 (14.6 engineering, medium): Production DDL executed outside IaC/CI
-- threshold: n/a; playbook: PB-ENG-IAC; autonomy: L1
SELECT USER_NAME AS OBJECT_NAME, count(*) AS OBSERVED FROM QUERY_HISTORY
WHERE (QUERY_TYPE LIKE 'CREATE%' OR QUERY_TYPE LIKE 'ALTER%' OR QUERY_TYPE LIKE 'DROP%')
  AND QUERY_TYPE NOT IN ('CREATE_TABLE_AS_SELECT')
  AND coalesce(QUERY_TAG, '') NOT IN ('terraform', 'dbt', 'schemachange')
GROUP BY 1 ORDER BY 1;
