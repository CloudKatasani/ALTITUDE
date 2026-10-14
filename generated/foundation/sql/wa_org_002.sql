-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-ORG-002 (14.1 organisation, low): Database name does not follow <ENV>_<DOMAIN>_<LAYER>
-- threshold: n/a; playbook: PB-ORG-NAMING; autonomy: L1
SELECT DISTINCT TABLE_CATALOG AS OBJECT_NAME, 'naming convention' AS DETAIL FROM TABLES
WHERE NOT regexp_matches(TABLE_CATALOG, '^(DEV|TEST|UAT|PROD)_[A-Z0-9]+_(RAW|CONFORMED|CURATED|SEMANTIC)$')
  AND TABLE_CATALOG NOT IN ('GOVERNANCE', 'OBS', 'SNOWFLAKE')
ORDER BY 1;
