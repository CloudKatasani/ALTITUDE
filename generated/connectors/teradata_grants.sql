-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/teradata.yaml. Regenerate with `altitude generate`.
-- Read-only grants for the extraction agent (CONN-TERADATA v1.0.0, teradata).
-- Principal: ALTITUDE_HARVEST (user). No write privilege is requested.

-- LOGON ON SYSTEM: Log on to the system; no data access is implied.
-- (granted by the platform administrator; no SQL form)

-- SELECT ON DBC (TablesV, ColumnsV, TableSizeV, AccessRightsV, DBCInfoV): Read the catalog, table sizes and access rights without reading any application table.
GRANT SELECT ON DBC TO ALTITUDE_HARVEST;

-- SELECT ON DBC.QryLogV, DBC.QryLogObjectsV: Read DBQL query and object logs for usage (counts and distinct users; query text parsed in-boundary).
GRANT SELECT ON DBC.QryLogV TO ALTITUDE_HARVEST; GRANT SELECT ON DBC.QryLogObjectsV TO ALTITUDE_HARVEST;
