<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/teradata.yaml. Regenerate with `altitude generate`. -->
# Permission manifest — teradata (CONN-TERADATA v1.0.0)

Read-only harvest of a Teradata system through DBC views and DBQL, plus BTEQ scripts read from the client's repository. Harvest at least a full fiscal year of DBQL to catch quarter and year-end jobs.

Principal: `ALTITUDE_HARVEST` (user). Row data read: **never**.

## Required grants

| Privilege | On | Why | Optional |
|---|---|---|---|
| LOGON | SYSTEM | Log on to the system; no data access is implied. | no |
| SELECT | DBC (TablesV, ColumnsV, TableSizeV, AccessRightsV, DBCInfoV) | Read the catalog, table sizes and access rights without reading any application table. | no |
| SELECT | DBC.QryLogV, DBC.QryLogObjectsV | Read DBQL query and object logs for usage (counts and distinct users; query text parsed in-boundary). | no |

## Objects read

| Object | Contains | Why |
|---|---|---|
| `DBC.TablesV` | catalog | Object inventory; RequestText holds view/macro/procedure DDL |
| `DBC.ColumnsV` | catalog | Columns incl. CASESPECIFIC and CHAR padding attributes |
| `DBC.TableSizeV` | statistics | Current perm space per table (aggregate) |
| `DBC.QryLogV` | usage | DBQL query log (time, user, statement type) |
| `DBC.QryLogObjectsV` | usage | DBQL object log (objects touched per query) |
| `DBC.AccessRightsV` | grants | Access rights for the target RBAC mapping |
| `DBC.DBCInfoV` | catalog | Release and version |

## Files read

- `**/*.bteq` — BTEQ scripts from the client's repository (code inventory and lineage)
- `**/*.btq` — BTEQ scripts (alternate extension)

## Never shipped

- user-table rows
- DBQL query text and literals
