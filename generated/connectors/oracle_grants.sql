-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/oracle.yaml. Regenerate with `altitude generate`.
-- Read-only grants for the extraction agent (CONN-ORACLE v1.0.0, oracle).
-- Principal: ALTITUDE_HARVEST (user). No write privilege is requested.

-- CREATE SESSION ON DATABASE: Log on; grants no read or write access to any schema object by itself.
GRANT CREATE SESSION TO ALTITUDE_HARVEST;

-- SELECT_CATALOG_ROLE ON DATABASE: Read DBA_* dictionary views (objects, source, columns, dependencies, scheduler jobs, privileges).
GRANT SELECT_CATALOG_ROLE TO ALTITUDE_HARVEST;

-- AUDIT_VIEWER ON DATABASE (optional): Read UNIFIED_AUDIT_TRAIL for object-level usage and distinct users.
GRANT AUDIT_VIEWER TO ALTITUDE_HARVEST;
