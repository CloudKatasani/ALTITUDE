<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/oracle.yaml. Regenerate with `altitude generate`. -->
# Permission manifest — oracle (CONN-ORACLE v1.0.0)

Read-only harvest of an Oracle (incl. Exadata) database through the data dictionary and the unified audit trail. AWR/ASH are deliberately not read: they require the Diagnostics Pack licence (OR-11).

Principal: `ALTITUDE_HARVEST` (user). Row data read: **never**.

## Required grants

| Privilege | On | Why | Optional |
|---|---|---|---|
| CREATE SESSION | DATABASE | Log on; grants no read or write access to any schema object by itself. | no |
| SELECT_CATALOG_ROLE | DATABASE | Read DBA_* dictionary views (objects, source, columns, dependencies, scheduler jobs, privileges). | no |
| AUDIT_VIEWER | DATABASE | Read UNIFIED_AUDIT_TRAIL for object-level usage and distinct users. | yes |

## Objects read

| Object | Contains | Why |
|---|---|---|
| `DBA_OBJECTS` | catalog | Object inventory with status and timestamps |
| `DBA_TABLES` | statistics | Table statistics (NUM_ROWS, BLOCKS) and temporary flag |
| `DBA_VIEWS` | code | View definitions |
| `DBA_SOURCE` | code | PL/SQL source (procedures, functions, packages, triggers) |
| `DBA_TAB_COLUMNS` | catalog | Column names, types, precision/scale, char semantics |
| `DBA_DEPENDENCIES` | dependencies | Dependency graph between objects |
| `DBA_SCHEDULER_JOBS` | schedule | DBMS_SCHEDULER job inventory and schedules |
| `DBA_SCHEDULER_JOB_RUN_DETAILS` | usage | Scheduler job run history |
| `DBA_TAB_PRIVS` | grants | Object grants for the target RBAC mapping |
| `DBA_ROLES` | grants | Distinguish role grantees from user grantees |
| `UNIFIED_AUDIT_TRAIL` | usage | Object-level access events (counts and distinct users only) |
| `PRODUCT_COMPONENT_VERSION` | catalog | Database version |

## Never shipped

- user-table rows
- audit SQL text and bind values
