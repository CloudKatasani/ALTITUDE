-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/well_architected/checks/identity_network.yaml. Regenerate with `altitude generate`.
-- WA-ORG-001 (14.1 organisation, high): Production database without replication / failover group
-- threshold: n/a; playbook: PB-ORG-FAILOVER; autonomy: L1
WITH prod AS (SELECT unnest(from_json("VALUE", '["VARCHAR"]')) AS DB FROM CLIENT_INPUTS WHERE "KEY" = 'production_databases')
SELECT DB AS OBJECT_NAME, 'no failover group covers this database' AS DETAIL FROM prod
WHERE NOT EXISTS (SELECT 1 FROM REPLICATION_GROUPS g
                  WHERE list_contains(string_split(replace(coalesce(g.ALLOWED_DATABASES, ''), ' ', ''), ','), prod.DB))
ORDER BY 1;
