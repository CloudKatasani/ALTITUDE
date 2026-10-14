<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/dialects/*/mappings.yaml. Regenerate with `altitude generate`. -->
# Conversion mappings

## teradata

| Id | Category | Source | Snowflake | Note | Issues |
|---|---|---|---|---|---|
| MAP-TD-001 | ddl | MULTISET table | Table | Direct | — |
| MAP-TD-002 | ddl | SET table | Table + explicit dedupe | Snowflake has no SET semantics | TD-01 |
| MAP-TD-003 | ddl | Primary Index / PPI / NUPI | None; clustering key only if justified | Do not emulate distribution | — |
| MAP-TD-004 | ddl | Volatile table | Temporary table | Session scope semantics differ slightly | — |
| MAP-TD-005 | procedural | Macro | Stored procedure / view |  | — |
| MAP-TD-006 | procedural | SPL stored procedure | Snowflake Scripting (SQL) | Cursor logic to set-based where possible | — |
| MAP-TD-007 | scripting | BTEQ script | Snowflake SQL + orchestrator / Snowflake CLI | Control flow (.IF ERRORCODE, .GOTO) must be rebuilt | TD-06 |
| MAP-TD-008 | loading | FastLoad / MultiLoad / TPT | COPY INTO / Snowpipe / Openflow |  | — |
| MAP-TD-009 | sql | QUALIFY | QUALIFY | Supported natively | — |
| MAP-TD-010 | sql | SAMPLE | SAMPLE / TABLESAMPLE | Semantics differ | — |
| MAP-TD-011 | types | PERIOD types | Two date/timestamp columns |  | — |
| MAP-TD-012 | ddl | COLLECT STATISTICS | Remove | Not applicable | — |
| MAP-TD-013 | types | NOT CASESPECIFIC columns | Collation spec or UPPER() normalisation | See issues | TD-02 |
| MAP-TD-014 | types | CHAR(n) | VARCHAR(n) with RTRIM at load | Pad semantics differ | TD-03 |
| MAP-TD-015 | types | TIMESTAMP(n) [WITH TIME ZONE] | TIMESTAMP_NTZ(n) / TIMESTAMP_TZ(n) per programme policy | Decide time-zone policy upfront | TD-11 |

## oracle

| Id | Category | Source | Snowflake | Note | Issues |
|---|---|---|---|---|---|
| MAP-OR-001 | types | NUMBER (no precision/scale) | NUMBER(38, s) with explicit scale, or FLOAT | Snowflake defaults scale 0 | OR-02 |
| MAP-OR-002 | types | VARCHAR2(n BYTE/CHAR) | VARCHAR(n) (characters) |  | OR-01 |
| MAP-OR-003 | types | DATE | TIMESTAMP_NTZ | Oracle DATE contains time | OR-03 |
| MAP-OR-004 | types | TIMESTAMP WITH LOCAL TIME ZONE | TIMESTAMP_LTZ |  | — |
| MAP-OR-005 | procedural | PL/SQL package | Schema + procedures/UDFs; package state to table/session variables | No packages | OR-04 |
| MAP-OR-006 | sql | CONNECT BY | CONNECT BY or recursive CTE | Supported; test ordering | — |
| MAP-OR-007 | ddl | Sequences | Sequences | Gaps, no CURRVAL parity in all contexts | — |
| MAP-OR-008 | procedural | Triggers | Streams + tasks, or move logic into pipelines | Not supported | OR-07 |
| MAP-OR-009 | sql | ROWNUM | ROW_NUMBER() / LIMIT |  | — |
| MAP-OR-010 | ddl | Materialized views | Dynamic tables (usually) | Snowflake MV restrictions | — |
| MAP-OR-011 | ddl | Global temporary tables | Temporary/transient tables |  | — |
| MAP-OR-012 | procedural | DBMS_* utilities | Rewritten | Case-by-case | — |
| MAP-OR-013 | integration | DB links | Data sharing / external access / pipelines |  | — |

## sqlserver

| Id | Category | Source | Snowflake | Note | Issues |
|---|---|---|---|---|---|
| MAP-MS-001 | procedural | T-SQL procedures | Snowflake Scripting / JavaScript / Python procedures |  | MS-05 |
| MAP-MS-002 | ddl | #temp / ##global tables | Temporary tables |  | — |
| MAP-MS-003 | ddl | IDENTITY | AUTOINCREMENT / IDENTITY |  | — |
| MAP-MS-004 | types | DATETIME / DATETIME2 / DATETIMEOFFSET | TIMESTAMP_NTZ / TIMESTAMP_TZ | DATETIME rounds to 1/300 s | MS-02 |
| MAP-MS-005 | types | UNIQUEIDENTIFIER | VARCHAR(36) (+ UUID_STRING()) |  | — |
| MAP-MS-006 | types | BIT | BOOLEAN |  | — |
| MAP-MS-007 | types | MONEY | NUMBER(19,4) |  | — |
| MAP-MS-008 | sql | CROSS/OUTER APPLY | LATERAL |  | — |
| MAP-MS-009 | sql | TOP n | LIMIT / TOP |  | — |
| MAP-MS-010 | scheduling | SQL Agent jobs | Tasks or external orchestrator |  | — |
| MAP-MS-011 | etl | SSIS | dbt + orchestrator / Openflow / Matillion etc. |  | MS-07 |
| MAP-MS-012 | bi | SSRS | Power BI paginated / other BI |  | — |
| MAP-MS-013 | integration | Linked servers | Pipelines / external access |  | — |
| MAP-MS-014 | procedural | CLR assemblies | Java/Python UDFs or redesign |  | — |

## netezza

| Id | Category | Source | Snowflake | Note | Issues |
|---|---|---|---|---|---|
| MAP-NZ-001 | ddl | DISTRIBUTE ON / ORGANIZE ON | Remove; clustering key only if justified |  | NZ-01 |
| MAP-NZ-002 | procedural | NZPLSQL procedures | Snowflake Scripting |  | NZ-02 |
| MAP-NZ-003 | loading | nzload | COPY INTO from staged files |  | NZ-03 |

## redshift

| Id | Category | Source | Snowflake | Note | Issues |
|---|---|---|---|---|---|
| MAP-RS-001 | ddl | DISTKEY / SORTKEY | Remove / clustering key |  | RS-05 |
| MAP-RS-002 | types | SUPER | VARIANT |  | — |
| MAP-RS-003 | integration | Spectrum external tables | External / Iceberg tables |  | — |
| MAP-RS-004 | workload | WLM queues | Warehouses |  | — |
| MAP-RS-005 | procedural | Stored procedures (PL/pgSQL) | Snowflake Scripting |  | — |
