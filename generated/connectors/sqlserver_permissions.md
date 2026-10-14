<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/sqlserver.yaml. Regenerate with `altitude generate`. -->
# Permission manifest — sqlserver (CONN-SQLSERVER v1.0.0)

Read-only harvest of a SQL Server / Azure SQL database: catalog, module code, column metadata, expression dependencies, plan-cache and Query Store usage, SQL Agent jobs and the SSIS catalog. The principal is never a member of db_datareader/db_owner and holds no permission on user tables.

Principal: `altitude_harvest` (login). Row data read: **never**.

## Required grants

| Privilege | On | Why | Optional |
|---|---|---|---|
| VIEW DEFINITION | DATABASE (each harvested database) | Read object definitions (sys.sql_modules) and catalog views without any access to table rows. | no |
| VIEW DATABASE STATE | DATABASE (each harvested database) | Read Query Store views and sys.dm_db_partition_stats (row counts and sizes, no rows). | no |
| VIEW SERVER STATE | SERVER | Read plan-cache usage (sys.dm_exec_procedure_stats, sys.dm_exec_query_stats) when Query Store is off. | no |
| SQLAgentReaderRole | msdb | Read SQL Agent job definitions, schedules and history (scheduler inventory and job usage). | no |
| ssis_logreader | SSISDB | Read the SSIS catalog (folders, projects, packages, executions) for ETL inventory and usage. | yes |

## Objects read

| Object | Contains | Why |
|---|---|---|
| `sys.objects` | catalog | Object inventory (tables, views, procedures, functions, triggers) |
| `sys.schemas` | catalog | Schema names for fully-qualified object names |
| `sys.sql_modules` | code | T-SQL source of views, procedures, functions and triggers |
| `sys.columns` | catalog | Column names, types, nullability and collation |
| `sys.types` | catalog | Column type names |
| `sys.sql_expression_dependencies` | dependencies | Static dependency graph between modules and tables |
| `sys.dm_exec_procedure_stats` | usage | Procedure execution counts and last execution time |
| `sys.dm_exec_query_stats` | usage | Ad hoc query usage when Query Store is disabled |
| `sys.database_query_store_options` | usage | Whether Query Store usage history is available |
| `sys.query_store_query` | usage | Query Store queries (owning module, text id) |
| `sys.query_store_query_text` | usage | Query text, parsed in-boundary for referenced objects; never shipped |
| `sys.query_store_plan` | usage | Plan to query mapping for runtime statistics |
| `sys.query_store_runtime_stats` | usage | Execution counts per plan and interval |
| `sys.query_store_runtime_stats_interval` | usage | Interval start/end times for usage periods |
| `sys.dm_db_partition_stats` | statistics | Table row counts and reserved pages (aggregates only) |
| `sys.database_permissions` | grants | Object-level grants for the target RBAC mapping |
| `sys.database_principals` | grants | Grantee names and types |
| `msdb.dbo.sysjobs` | schedule | SQL Agent job inventory |
| `msdb.dbo.sysjobsteps` | schedule | Job step commands (procedures and packages they run) |
| `msdb.dbo.sysjobschedules` | schedule | Job to schedule mapping |
| `msdb.dbo.sysschedules` | schedule | Schedule frequency (daily, weekly, monthly / month-end) |
| `msdb.dbo.sysjobhistory` | usage | Job run history (job usage) |
| `SSISDB.catalog.folders` | etl | SSIS catalog folders |
| `SSISDB.catalog.projects` | etl | SSIS projects |
| `SSISDB.catalog.packages` | etl | SSIS package inventory |
| `SSISDB.catalog.executions` | usage | SSIS package executions (ETL usage) |

## Files read

- `**/*.dtsx` — SSIS package definitions from the client's repository (extracted SQL and task types only)

## Never shipped

- user-table rows
- query text (parsed in-boundary; only object names and counts leave)
- parameter values and plan XML
