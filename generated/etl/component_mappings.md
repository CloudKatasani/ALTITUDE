<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/etl/*.yaml, knowledge/schedulers/*.yaml. Regenerate with `altitude generate`. -->
# ETL component and scheduler catalogue

Rendered from `knowledge/etl` and `knowledge/schedulers`; edit the YAML, then `altitude generate`.

## ssis

| Component | Kind | Target | Known issue |
|---|---|---|---|
| Microsoft.OLEDBSource, Microsoft.ADONETSource | source | dbt source + stg_ model |  |
| Microsoft.FlatFileSource, Microsoft.ExcelSource | source | stage + COPY INTO landing table, then dbt source | ETL-GEN-02 |
| Microsoft.DerivedColumn, {49928E82-9C4E-49F0-AABE-3812B82707EC} | project | column expressions in int_ model |  |
| Microsoft.DataConvert | project | CAST in int_ model |  |
| Microsoft.Lookup, {671046B0-AA63-4C9F-90E4-C06E0B710CE3} | lookup | LEFT JOIN to deduplicated reference model | ETL-SSIS-04 |
| Microsoft.ConditionalSplit, {7F88F654-4E20-4D14-84F4-AF9C925D3087} | split | first-match WHERE predicates per output | ETL-SSIS-05 |
| Microsoft.Multicast | passthrough | shared upstream model referenced by several models |  |
| Microsoft.UnionAll, Microsoft.Merge | union | UNION ALL |  |
| Microsoft.MergeJoin | join | JOIN (sort inputs no longer required) |  |
| Microsoft.Aggregate | aggregate | GROUP BY in agg_ / int_ model |  |
| Microsoft.Sort | sort | removed (ordering is not a table property); DISTINCT when EliminateDuplicates |  |
| Microsoft.RowCount | passthrough | removed; row counts come from query history / dbt run results |  |
| Microsoft.OLEDBDestination, Microsoft.ADONETDestination | target | dim_/fct_/agg_ model |  |
| Microsoft.FlatFileDestination, Microsoft.ExcelDestination | target | COPY INTO @stage (unload) after the model | ETL-GEN-02 |
| Microsoft.SCD | unsupported | dbt snapshot (re-engineer) | ETL-SSIS-06 |
| Microsoft.ScriptComponentHost | unsupported | re-engineer (Snowpark / SQL); never convert C# blindly | ETL-SSIS-01 |
| Microsoft.OLEDBCommand | unsupported | set-based MERGE in an incremental model | ETL-GEN-01 |
| Microsoft.Pivot, Microsoft.UnPivot | unsupported | re-engineer (PIVOT/UNPIVOT or Cortex functions) |  |
| Microsoft.Pipeline, SSIS.Pipeline.3 | data_flow | dbt models (one job per data flow) |  |
| Microsoft.ExecuteSQLTask, Microsoft.SqlServer.Dts.Tasks.ExecuteSQLTask.ExecuteSQLTask | sql_task | dbt macro (run-operation) or pre/post-hook; TRUNCATE before full reload is retired |  |
| Microsoft.ScriptTask, Microsoft.SqlServer.Dts.Tasks.ScriptTask.ScriptTask | script_task | re-engineer (Snowpark Python / external function) | ETL-SSIS-01 |
| STOCK:SEQUENCE, STOCK:FORLOOP | container | orchestrator task group; FOREACH loops become set-based models or Snowflake Scripting loops |  |
| Microsoft.ExecutePackageTask | package_call | task-graph dependency |  |
| Microsoft.SendMailTask | notification | Snowflake notification integration / orchestrator alert |  |
| Microsoft.FileSystemTask, Microsoft.FtpTask | file_task | stages + external access integration | ETL-GEN-02 |

## informatica

| Component | Kind | Target | Known issue |
|---|---|---|---|
| Source Definition | source | dbt source + stg_ model |  |
| Source Qualifier, Application Source Qualifier | project | column selection + source filter in int_ model; SQL overrides are re-engineered | ETL-INF-04 |
| Expression | project | column expressions in int_ model | ETL-INF-06 |
| Filter | filter | WHERE predicate |  |
| Lookup Procedure, Lookup | lookup | LEFT JOIN to deduplicated reference model (cache semantics become set-based) | ETL-INF-02 |
| Aggregator | aggregate | GROUP BY in agg_ / int_ model |  |
| Joiner | join | JOIN (master/detail outer semantics mapped explicitly) |  |
| Router | split | one WHERE predicate per group (a row can reach several groups) | ETL-INF-03 |
| Union, Custom Transformation/Union | union | UNION ALL | ETL-INF-03 |
| Sorter | sort | removed; DISTINCT when 'Distinct' is set |  |
| Sequence, Sequence Generator | sequence | ROW_NUMBER() surrogate key (or a Snowflake sequence for incremental loads) |  |
| Target Definition | target | dim_/fct_/agg_ model |  |
| Update Strategy | unsupported | incremental model with unique_key (MERGE) | ETL-INF-07 |
| Mapplet, Mapplet Input | unsupported | dbt macro or ephemeral model per mapplet | ETL-INF-01 |
| Java, Stored Procedure | unsupported | re-engineer (Snowpark / SQL) | ETL-INF-06 |

## Known issues

| Id | Severity | Title | Fix |
|---|---|---|---|
| ETL-ABI-01 | S2 | Proprietary components and PDL | Re-engineer per component family. |
| ETL-DS-01 | S2 | Parallel job partitioning, transformer stage variables and sequence jobs | Drop partitioning; rewrite stage variables as window functions; sequences to the orchestrator. |
| ETL-GEN-01 | S3 | Row-by-row commands against the warehouse | Set-based MERGE in an incremental model. |
| ETL-GEN-02 | S2 | File-system side effects and file-based sources/targets | Stages, COPY INTO and directory tables; external access integrations for remote systems. |
| ETL-GEN-03 | S2 | Expression not translatable to SQL | Manual rewrite; extend the function map in knowledge if the construct recurs. |
| ETL-GEN-04 | S3 | Execute SQL task with dialect-specific SQL | Convert with the conversion orchestrator (SnowConvert AI) and review. |
| ETL-HAND-01 | S2 | Undocumented control flow and file-system side effects in shell + SQL | Map control flow to the orchestrator; files to stages. |
| ETL-INF-01 | S2 | Mapplets hide reusable logic that must be expanded or rebuilt | Rebuild each mapplet once as a dbt macro or ephemeral model; reuse across mappings. |
| ETL-INF-02 | S1 | Lookups with caches (static/dynamic) and multi-match policies | Deduplicate the reference model explicitly (ROW_NUMBER) and test uniqueness; dynamic caches become incremental MERGE logic. |
| ETL-INF-03 | S1 | Router and Union semantics | Generate one predicate per group without first-match short-circuit; NULL conditions count as false; reconcile group counts. |
| ETL-INF-04 | S2 | Session and Source Qualifier SQL overrides | Re-engineer the override as a model; overrides bypass the mapping graph and are dialect-specific SQL. |
| ETL-INF-05 | S2 | Parameter files and mapping variables | Map parameters to dbt vars with explicit defaults per environment; inventory the parameter files. |
| ETL-INF-06 | S2 | Row-by-row expression logic (variable ports, unconnected lookups, Java) | Rewrite as set-based SQL (window functions, joins); re-engineer code transformations. |
| ETL-INF-07 | S2 | Update Strategy (DD_UPDATE/DD_DELETE) requires incremental merge design | Incremental model with unique_key / MERGE; deletes become soft-deletes or explicit DELETE models. |
| ETL-ODI-01 | S2 | Knowledge modules embed SQL dialect | Regenerate logic as dbt models; do not port KMs. |
| ETL-SSIS-01 | S2 | Script tasks and script components (C#/VB) | Re-engineer; never convert script code blindly (MS-07). |
| ETL-SSIS-02 | S2 | Event handlers | Move to orchestrator failure callbacks / finalizer tasks and alerts. |
| ETL-SSIS-03 | S2 | Package configurations, parameters and variables | Map to dbt vars / environment config; inventory configuration sources (XML files, SQL tables, env vars). |
| ETL-SSIS-04 | S1 | Lookup cache and no-match behaviour | LEFT JOIN to a deduplicated reference model; rows failing the lookup are kept (redirect/fail behaviour handled by tests). |
| ETL-SSIS-05 | S1 | Conditional Split is first-match | Each output predicate excludes rows matched by earlier outputs (ordered evaluation preserved). |
| ETL-SSIS-06 | S2 | Slowly Changing Dimension wizard | Replace with dbt snapshots (check/timestamp strategy). |
| ETL-TAL-01 | S2 | Java routines in Talend jobs | Re-engineer as SQL or Snowpark. |
| SCH-01 | S2 | Calendar-based logic (business days, fiscal calendars) | Cron approximates the window; gate the root task on a calendar table (WHEN / first step) and test against the calendar. |
| SCH-02 | S2 | Cross-system dependencies (file arrivals, upstream jobs outside the export) | Model as an explicit sensor (directory table stream / external event table) feeding the root task. |
| SCH-03 | S3 | Restart and rerun semantics | Snowflake retries apply to the whole task graph (TASK_AUTO_RETRY_ATTEMPTS on the root); per-step retries live in Airflow. |
| SCH-04 | S3 | SLA alerting | Snowflake alerts on TASK_HISTORY for deadlines; Airflow sla / execution_timeout per task. |
| SCH-05 | S3 | Job both scheduled and triggered by another job | A task graph child cannot have a schedule; the schedule is dropped and the dependency kept - confirm intent. |
| SCH-06 | S3 | Failure-path steps | Becomes the graph finalizer task (Snowflake FINALIZE) and a one_failed trigger rule in Airflow. |
| SCH-07 | S2 | Command without a mapping | Placeholder task keeps the graph intact; convert the command and add a mapping rule. |
| SCH-08 | S3 | Roots with different schedules merged into one graph | A synthetic root runs on the earliest schedule; confirm or split the graph. |

## Scheduler command mappings

| Id | Snowflake body | Note |
|---|---|---|
| CMD-SSIS-DTEXEC | `EXECUTE DBT PROJECT {dbt_project} ARGS = 'build --select tag:{tag}'` | SSIS package re-engineered as dbt models tagged with the package name. |
| CMD-SSIS-CATALOG | `EXECUTE DBT PROJECT {dbt_project} ARGS = 'build --select tag:{tag}'` | SSIS catalog package (SQL Agent SSIS subsystem) re-engineered as tagged dbt models. |
| CMD-INFA-PMCMD | `EXECUTE DBT PROJECT {dbt_project} ARGS = 'build --select tag:{tag}'` | Informatica workflow re-engineered as tagged dbt models. |
| CMD-DBT | `EXECUTE DBT PROJECT {dbt_project} ARGS = '{args}'` | dbt CLI call mapped to dbt Projects on Snowflake. |
| CMD-BTEQ | `EXECUTE IMMEDIATE FROM {script_stage}/{name}.sql` | BTEQ script converted by the conversion orchestrator and staged. |
| CMD-TSQL-DBMAIL | `CALL SYSTEM$SEND_EMAIL('{notification_integration}', '{to}', '{subject}', 'Sent by the task graph')` | Database Mail notification mapped to a Snowflake notification integration. |
| CMD-SQLCMD-PROC | `CALL {proc}()` | Stored procedure converted by the conversion orchestrator. |
| CMD-TSQL-PROC | `CALL {proc}()` | T-SQL step executing a stored procedure. |
| CMD-TSQL-TRUNCATE | `{stmt}` | Truncate statement (retire if the downstream model is a full-refresh table). |
| CMD-SHELL-SCRIPT | `EXECUTE IMMEDIATE FROM {script_stage}/{name}.sql` | Shell script whose SQL steps are staged after conversion; file-system side effects need review. |
