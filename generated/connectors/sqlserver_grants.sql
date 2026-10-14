-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/connectors/sqlserver.yaml. Regenerate with `altitude generate`.
-- Read-only grants for the extraction agent (CONN-SQLSERVER v1.0.0, sqlserver).
-- Principal: altitude_harvest (login). No write privilege is requested.

-- VIEW DEFINITION ON DATABASE (each harvested database): Read object definitions (sys.sql_modules) and catalog views without any access to table rows.
GRANT VIEW DEFINITION TO altitude_harvest;

-- VIEW DATABASE STATE ON DATABASE (each harvested database): Read Query Store views and sys.dm_db_partition_stats (row counts and sizes, no rows).
GRANT VIEW DATABASE STATE TO altitude_harvest;

-- VIEW SERVER STATE ON SERVER: Read plan-cache usage (sys.dm_exec_procedure_stats, sys.dm_exec_query_stats) when Query Store is off.
GRANT VIEW SERVER STATE TO altitude_harvest;

-- SQLAgentReaderRole ON msdb: Read SQL Agent job definitions, schedules and history (scheduler inventory and job usage).
USE msdb; ALTER ROLE SQLAgentReaderRole ADD MEMBER altitude_harvest;

-- ssis_logreader ON SSISDB (optional): Read the SSIS catalog (folders, projects, packages, executions) for ETL inventory and usage.
USE SSISDB; ALTER ROLE ssis_logreader ADD MEMBER altitude_harvest;
