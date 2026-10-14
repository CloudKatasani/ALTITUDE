<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/dialects/**, knowledge/rubrics/*.yaml. Regenerate with `altitude generate`. -->
# Known-issues catalogue

Pattern Library `patterns:ed7676ba9852` — 47 issues (S1: 19, S2: 15, S3: 8, S4: 5). Severity: S1 silent wrong answers · S2 failure/rewrite · S3 performance/cost · S4 cosmetic/operational.

## teradata

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| TD-01 | S1 | SET tables silently discarded duplicate rows on insert; Snowflake keeps them | `static.td_set_table` | FX-TD-01-A | 3 |
| TD-02 | S1 | Case-insensitive comparisons (NOT CASESPECIFIC, Teradata session mode) become case-sensitive | `static.td_case_insensitive` | FX-TD-02-A | 2 |
| TD-03 | S1 | Trailing-space handling in CHAR comparisons differs | `static.td_char_columns` | FX-TD-03-A | 1 |
| TD-04 | S1 | Integer date arithmetic and date-format literals (CYYMMDD integers vs dates) | `static.td_integer_date` | FX-TD-04-A | 1 |
| TD-05 | S1 | Division of integers returns an integer in Teradata; Snowflake returns a decimal | `static.int_division` | FX-TD-05-A | 2 |
| TD-06 | S2 | BTEQ error handling and .ACTIVITYCOUNT control flow must be rebuilt | `static.td_bteq_control` | FX-TD-06-A | 1 |
| TD-07 | S3 | Recursive views and deep view stacks perform differently | `profile.view_depth` | FX-TD-07-A | 1 |
| TD-08 | S1 | Teradata-style UPDATE ... FROM with joins and ambiguous multi-match updates | `static.update_from_join` | FX-TD-08-A | 2 |
| TD-09 | S3 | TASM workload priorities have no 1:1 equivalent | `profile.tasm_workloads` | FX-TD-09-A | 1 |
| TD-10 | S4 | Identity columns and GENERATED ALWAYS gaps | `static.identity_columns` | FX-TD-10-A | 1 |
| TD-11 | S1 | Timestamp precision and time-zone session defaults | `static.td_timestamp_tz` | FX-TD-11-A | 2 |

### TD-01 — SET tables silently discarded duplicate rows on insert; Snowflake keeps them

Severity **S1** · checklist items 6 · decision required: yes · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Target row count exceeds source after loading the same batch
- COUNT(*) and SUM() on the migrated table are higher than on Teradata; COUNT(DISTINCT *) matches

Detection (static_and_profile): CREATE SET TABLE (or CREATE TABLE without MULTISET in Teradata session mode) plus every INSERT into such a table; Table kind = SET in DBC.TablesV, or target row count > source distinct row count after load. Detectors: `static.td_set_table`, `profile.set_table_duplicates`.

Fix patterns:

- **FX-TD-01-A** — Dedupe in the load: INSERT ... SELECT ... QUALIFY ROW_NUMBER() OVER (PARTITION BY <all columns> ORDER BY <all columns>) = 1, or SELECT DISTINCT *(when: Programme policy = preserve_set_semantics (default))*
- **FX-TD-01-B** — MERGE on the full row (or natural key) so re-delivered duplicates are ignored *(when: Incremental loads with a natural key)*

Tests: TC-TD-01-001, TC-TD-01-101, TC-TD-01-102. Validation normalisation: L1 compares source distinct row count with target row count; L3 keyed duplicates cluster to TD-01

### TD-02 — Case-insensitive comparisons (NOT CASESPECIFIC, Teradata session mode) become case-sensitive

Severity **S1** · checklist items 1, 7 · decision required: yes · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Filters on literal strings return fewer rows in Snowflake
- Joins on code columns drop rows whose case differs; GROUP BY splits case variants

Detection (static_and_profile): NOT CASESPECIFIC / (NOT CS) column attributes, BTET session mode, predicates on such columns; DBC.ColumnsV.UpperCaseFlag = N for character columns used in joins/filters. Detectors: `static.td_case_insensitive`, `profile.case_insensitive_columns`.

Fix patterns:

- **FX-TD-02-A** — Declare the column with COLLATE 'en-ci' (programme collation policy) and retest joins/filters *(when: Policy = case_insensitive_collation)*
- **FX-TD-02-B** — Normalise at ingestion (UPPER) or compare UPPER(col) = UPPER(:value) in rewritten predicates *(when: Policy = normalise_case)*

Tests: TC-TD-02-001, TC-TD-02-101. Validation normalisation: Case-fold string columns for L3 hashing only when policy normalise_case is applied

### TD-03 — Trailing-space handling in CHAR comparisons differs

Severity **S1** · checklist items 5 · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Joins between CHAR(n) exports and VARCHAR columns return no rows
- String lengths differ (LENGTH counts pad characters)

Detection (static): CHAR(n)/CHARACTER(n) columns, especially those used in joins and equality predicates; Source CHAR(n) column mapped to VARCHAR without RTRIM in the load. Detectors: `static.td_char_columns`, `profile.char_padding`.

Fix patterns:

- **FX-TD-03-A** — RTRIM at load and convert CHAR(n) to VARCHAR(n) *(when: Default)*
- **FX-TD-03-B** — Compare RTRIM(a) = RTRIM(b) in rewritten joins when raw values must be preserved *(when: Raw layer must preserve exact source values)*

Tests: TC-TD-03-001. Validation normalisation: RTRIM string columns before L3 hashing when policy char_padding_ignored is applied

### TD-04 — Integer date arithmetic and date-format literals (CYYMMDD integers vs dates)

Severity **S1** · checklist items 4, 9 · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Dates land in 1970 (integer interpreted as epoch seconds) or conversions fail
- Filters on integer date literals such as 1260101 silently match nothing

Detection (static): CAST(int AS DATE), CAST(date AS INTEGER), CYYMMDD integer literals, (DATE) casts and FORMAT clauses. Detectors: `static.td_integer_date`.

Fix patterns:

- **FX-TD-04-A** — Decode Teradata integer dates explicitly: DATE_FROM_PARTS(1900 + FLOOR(d / 10000), MOD(FLOOR(d / 100), 100), MOD(d, 100)) *(when: Integer-encoded dates in source columns or literals)*
- **FX-TD-04-B** — Replace integer date arithmetic with DATEADD/DATEDIFF and explicit casts *(when: Arithmetic on dates)*

Tests: TC-TD-04-001. Validation normalisation: None; mismatches are real defects

### TD-05 — Division of integers returns an integer in Teradata; Snowflake returns a decimal

Severity **S1** · checklist items 3 · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Averages and ratios gain decimals; downstream joins on computed buckets break

Detection (static): Integer expression / integer expression (literals, COUNT, INTEGER columns). Detectors: `static.int_division`.

Fix patterns:

- **FX-TD-05-A** — Make intent explicit: TRUNC(a / b) (or FLOOR for non-negative values) to keep integer semantics *(when: Integer result was intended)*
- **FX-TD-05-B** — Cast one operand to NUMBER(p,s) when decimals were intended and the source was a latent bug (decision required) *(when: Business confirms decimal intent)*

Tests: TC-TD-05-001, TC-TD-05-101. Validation normalisation: None

### TD-06 — BTEQ error handling and .ACTIVITYCOUNT control flow must be rebuilt

Severity **S2** · checklist items 12 · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Converted scripts continue after failures or skip steps

Detection (static): .IF ERRORCODE/.ACTIVITYCOUNT, .GOTO/.LABEL, .QUIT, .ERRORLEVEL dot-commands. Detectors: `static.td_bteq_control`.

Fix patterns:

- **FX-TD-06-A** — Rebuild as Snowflake Scripting with EXCEPTION blocks and SQLROWCOUNT, orchestrated by tasks or an external orchestrator *(when: Always)*

Tests: TC-TD-06-101. Validation normalisation: None

### TD-07 — Recursive views and deep view stacks perform differently

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Queries over view stacks are slower and more expensive in Snowflake

Detection (profile): CREATE RECURSIVE VIEW / WITH RECURSIVE; View dependency depth above rubric.patterns.profile.view_depth_max. Detectors: `profile.view_depth`, `static.recursive_view`.

Fix patterns:

- **FX-TD-07-A** — Materialise intermediate layers as dynamic tables; flatten view stacks *(when: Depth above rubric limit and the stack is queried frequently)*

Tests: TC-TD-07-101. Validation normalisation: None

### TD-08 — Teradata-style UPDATE ... FROM with joins and ambiguous multi-match updates

Severity **S1** · checklist items 8 · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Updated values differ between runs or from the source baseline
- Snowflake raises 'Duplicate row detected during DML action' when ERROR_ON_NONDETERMINISTIC_UPDATE is set

Detection (static_and_profile): UPDATE <t> FROM <t>, <s> / UPDATE ... SET ... FROM joins and MERGE with a source that may be non-unique on the join key; Join key of the update source is not unique (distinct count < row count). Detectors: `static.update_from_join`, `profile.update_source_uniqueness`.

Fix patterns:

- **FX-TD-08-A** — Pre-aggregate or dedupe the update source to one row per target key (GROUP BY key / QUALIFY ROW_NUMBER() = 1) *(when: Always for multi-match sources)*

Tests: TC-TD-08-001, TC-TD-08-101. Validation normalisation: None

### TD-09 — TASM workload priorities have no 1:1 equivalent

Severity **S3** · checklist items — · decision required: yes · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Mixed workloads contend after cutover; SLAs slip at peak

Detection (profile): TASM/TIWM workload definitions present in the harvest. Detectors: `profile.tasm_workloads`.

Fix patterns:

- **FX-TD-09-A** — Map workloads to dedicated warehouses with resource monitors and query acceleration where justified *(when: Always)*

Tests: TC-TD-09-101. Validation normalisation: None

### TD-10 — Identity columns and GENERATED ALWAYS gaps

Severity **S4** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Surrogate key values differ or have gaps after migration

Detection (static): GENERATED ALWAYS|BY DEFAULT AS IDENTITY in DDL. Detectors: `static.identity_columns`.

Fix patterns:

- **FX-TD-10-A** — Use sequences/AUTOINCREMENT; never assume gap-free or ordered values; carry source keys during migration *(when: Always)*

Tests: TC-TD-10-101. Validation normalisation: Exclude generated surrogate keys from L3 hashing when re-generated in target

### TD-11 — Timestamp precision and time-zone session defaults

Severity **S1** · checklist items 4, 11 · decision required: yes · last verified 2026-10-01 by practice-lead-teradata.

Symptoms:

- Daily aggregates shift rows across day boundaries
- Timestamps differ by whole hours or in fractional seconds

Detection (static_and_profile): SET TIME ZONE, AT LOCAL/AT TIME ZONE, TIMESTAMP(n) WITH TIME ZONE, CAST(timestamp AS DATE); DBS Control / session time zone not UTC in the settings harvest. Detectors: `static.td_timestamp_tz`, `profile.session_timezone`.

Fix patterns:

- **FX-TD-11-A** — Standardise a TIMESTAMP_NTZ (UTC) vs TIMESTAMP_TZ policy upfront; convert explicitly with CONVERT_TIMEZONE where business days are local *(when: Always (programme-level ADR))*

Tests: TC-TD-11-001, TC-TD-11-101. Validation normalisation: Compare timestamps in UTC at the agreed precision

## oracle

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| OR-01 | S1 | Empty string treated as NULL in Oracle; distinct value in Snowflake | `static.or_empty_string_null` | FX-OR-01-A | 3 |
| OR-02 | S1 | Unscaled NUMBER mapped to scale 0 truncates decimals | `static.or_unscaled_number` | FX-OR-02-A | 2 |
| OR-03 | S1 | Oracle DATE time component lost when mapped to DATE | `static.or_date_type` | FX-OR-03-A | 2 |
| OR-04 | S2 | Packages with global state, overloading and autonomous transactions | `static.or_package_state` | FX-OR-04-A | 1 |
| OR-05 | S3 | Row-by-row BULK COLLECT / cursor loops | `static.cursor_loops` | FX-OR-05-A | 1 |
| OR-06 | S2 | Legacy (+) outer joins | `static.or_outer_join_plus` | FX-OR-06-A | 1 |
| OR-07 | S2 | Triggers used for audit or derivation | `static.triggers` | FX-OR-07-A | 1 |
| OR-08 | S1 | NLS_* session settings drive date formats, sort and comparison | `static.or_nls` | FX-OR-08-A | 2 |
| OR-09 | S2 | LOB sizes, LONG, XMLTYPE and spatial types | `static.or_lob_types` | FX-OR-09-A | 1 |
| OR-10 | S3 | Exadata performance relied on smart scan, HCC and partition pruning | `profile.exadata_features` | FX-OR-10-A | 1 |
| OR-11 | S4 | Oracle licensing exposure during migration (extra cores for unload, diagnostic packs) | `profile.licensing_exposure` | FX-OR-11-A | 1 |

### OR-01 — Empty string treated as NULL in Oracle; distinct value in Snowflake

Severity **S1** · checklist items 2 · decision required: yes · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Row counts match but COUNT(col) and IS NULL filters differ
- String concatenation results differ

Detection (static_and_profile): Predicates using IS NULL / IS NOT NULL / NVL / COALESCE on VARCHAR2 columns, comparisons with '' and || concatenation; Null-count on Snowflake side lower than source for same column after load. Detectors: `static.or_empty_string_null`, `profile.null_count_delta`.

Fix patterns:

- **FX-OR-01-A** — Normalise at ingestion: NULLIF(TRIM(col), '') for VARCHAR columns in raw to silver *(when: Programme policy = oracle_null_semantics)*
- **FX-OR-01-B** — Rewrite predicates: (col IS NULL OR col = ''); wrap concatenation operands in COALESCE(col, '') *(when: Raw layer must preserve exact source values)*

Tests: TC-OR-01-001, TC-OR-01-002, TC-OR-01-101. Validation normalisation: Treat '' and NULL as equal for L3 hashing when policy A applied

### OR-02 — Unscaled NUMBER mapped to scale 0 truncates decimals

Severity **S1** · checklist items 3 · decision required: yes · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- SUM/AVG differ; amounts rounded to whole units

Detection (static_and_profile): NUMBER without precision/scale (or NUMBER(*)) in DDL, PL/SQL declarations and casts; Profiled max scale of the source column exceeds the target column scale. Detectors: `static.or_unscaled_number`, `profile.max_scale`.

Fix patterns:

- **FX-OR-02-A** — Profile max scale (metadata stats or permission-gated sample) and declare NUMBER(38, s) explicitly *(when: Always)*
- **FX-OR-02-B** — Map to FLOAT only for genuinely approximate measures (checklist item 10 applies) *(when: Scientific/approximate values)*

Tests: TC-OR-02-001, TC-OR-02-101. Validation normalisation: Canonical decimal rendering only; never round to the target scale

### OR-03 — Oracle DATE time component lost when mapped to DATE

Severity **S1** · checklist items 4 · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Intraday filters and ordering differ; timestamps show midnight

Detection (static_and_profile): DATE columns in DDL, SYSDATE, TO_DATE with time formats, TRUNC(date); Source DATE column has non-midnight values and the target type is DATE. Detectors: `static.or_date_type`, `profile.date_time_component`.

Fix patterns:

- **FX-OR-03-A** — Map Oracle DATE to TIMESTAMP_NTZ; fix downstream comparisons that relied on TRUNC *(when: Always)*

Tests: TC-OR-03-001, TC-OR-03-101. Validation normalisation: None

### OR-04 — Packages with global state, overloading and autonomous transactions

Severity **S2** · checklist items 12 · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Converted procedures lose package state between calls; logging rolls back with the caller

Detection (static): CREATE PACKAGE [BODY], package-level variables, PRAGMA AUTONOMOUS_TRANSACTION. Detectors: `static.or_package_state`.

Fix patterns:

- **FX-OR-04-A** — Decompose into schema + procedures/UDFs; move state into tables or session variables; redesign autonomous logging *(when: Always)*

Tests: TC-OR-04-101. Validation normalisation: None

### OR-05 — Row-by-row BULK COLLECT / cursor loops

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Converted procedures are slow and expensive

Detection (static): BULK COLLECT, FORALL, explicit cursors, FOR rec IN (SELECT ...) loops. Detectors: `static.cursor_loops`.

Fix patterns:

- **FX-OR-05-A** — Set-based rewrite (INSERT ... SELECT / MERGE); AI refactor agent with generated unit tests *(when: Always)*

Tests: TC-OR-05-101. Validation normalisation: None

### OR-06 — Legacy (+) outer joins

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Conversion errors or inner-join semantics after naive rewrite

Detection (static): (+) operator in WHERE clauses. Detectors: `static.or_outer_join_plus`.

Fix patterns:

- **FX-OR-06-A** — Convert to ANSI LEFT/RIGHT OUTER JOIN, keeping filter predicates on the optional side in the ON clause *(when: Always)*

Tests: TC-OR-06-101. Validation normalisation: None

### OR-07 — Triggers used for audit or derivation

Severity **S2** · checklist items 6 · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Audit columns or derived values stop being populated

Detection (static): CREATE [OR REPLACE] TRIGGER. Detectors: `static.triggers`.

Fix patterns:

- **FX-OR-07-A** — Streams + tasks or pipeline logic; audit via ACCESS_HISTORY *(when: Always)*

Tests: TC-OR-07-101. Validation normalisation: None

### OR-08 — NLS_* session settings drive date formats, sort and comparison

Severity **S1** · checklist items 11, 7 · decision required: yes · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Date strings render differently (01-OCT-26 vs 2026-10-01); string sort order differs

Detection (static_and_profile): ALTER SESSION SET NLS_*, TO_CHAR/TO_DATE without an explicit format model; Non-default NLS_DATE_FORMAT / NLS_SORT / NLS_COMP in the settings harvest. Detectors: `static.or_nls`, `profile.nls_settings`.

Fix patterns:

- **FX-OR-08-A** — Harvest NLS settings and make every format explicit, e.g. UPPER(TO_CHAR(d, 'DD-MON-YY')) to reproduce NLS_DATE_FORMAT=DD-MON-RR *(when: Always)*

Tests: TC-OR-08-001, TC-OR-08-101. Validation normalisation: None

### OR-09 — LOB sizes, LONG, XMLTYPE and spatial types

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Load failures on oversized values; XML/spatial functions unavailable

Detection (static): LONG, LONG RAW, CLOB/BLOB/NCLOB, BFILE, XMLTYPE, SDO_GEOMETRY. Detectors: `static.or_lob_types`.

Fix patterns:

- **FX-OR-09-A** — Check current Snowflake size limits; VARIANT/GEOGRAPHY; externalise large binaries to object storage *(when: Always)*

Tests: TC-OR-09-101. Validation normalisation: None

### OR-10 — Exadata performance relied on smart scan, HCC and partition pruning

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Large scans slower than on Exadata until clustering/pruning is designed

Detection (profile): COMPRESS FOR QUERY/ARCHIVE, PARALLEL degree clauses; Exadata features (smart scan, HCC) present in the platform harvest. Detectors: `profile.exadata_features`, `static.or_exadata_storage`.

Fix patterns:

- **FX-OR-10-A** — Clustering keys only for very large, frequently filtered tables; measure first *(when: After L5 performance baseline)*

Tests: TC-OR-10-101. Validation normalisation: None

### OR-11 — Oracle licensing exposure during migration (extra cores for unload, diagnostic packs)

Severity **S4** · checklist items — · decision required: yes · last verified 2026-10-01 by practice-lead-oracle.

Symptoms:

- Unplanned licence true-up after AWR/ASH use or extra unload cores

Detection (profile): Diagnostics/Tuning Pack usage or planned unload capacity above licensed cores. Detectors: `profile.licensing_exposure`.

Fix patterns:

- **FX-OR-11-A** — Licence review in Phase 0; use DBA_* views instead of AWR when packs are not licensed *(when: Always)*

Tests: TC-OR-11-101. Validation normalisation: None

## sqlserver

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| MS-01 | S1 | Default case-insensitive collation; Snowflake is case-sensitive | `static.ms_case_insensitive` | FX-MS-01-A | 3 |
| MS-02 | S1 | DATETIME rounding (1/300 s, about 3 ms) vs Snowflake precision | `static.ms_datetime_precision` | FX-MS-02-A | 2 |
| MS-03 | S4 | NOLOCK and isolation hints assume the locking model | `static.ms_nolock` | FX-MS-03-A | 1 |
| MS-04 | S1 | Implicit conversions (string to number, string to date) | `static.ms_implicit_conversion` | FX-MS-04-A | 1 |
| MS-05 | S2 | Error handling with TRY/CATCH, @@ERROR, @@ROWCOUNT, RAISERROR | `static.ms_error_handling` | FX-MS-05-A | 1 |
| MS-06 | S2 | Dynamic SQL built from strings | `static.ms_dynamic_sql` | FX-MS-06-A | 1 |
| MS-07 | S2 | SSIS packages with script tasks (C#) | `static.ms_ssis_script_task` | FX-MS-07-A | 1 |
| MS-08 | S1 | Triggers and cascading foreign keys enforce integrity that Snowflake does not | `static.constraints_enforcement` | FX-MS-08-A | 2 |
| MS-09 | S3 | Row-by-row OLTP patterns pointed at the warehouse | `static.cursor_loops` | FX-MS-09-A | 1 |
| MS-10 | S3 | Synapse distribution and columnstore tuning emulation | `static.ms_synapse_distribution` | FX-MS-10-A | 1 |

### MS-01 — Default case-insensitive collation; Snowflake is case-sensitive

Severity **S1** · checklist items 1, 7 · decision required: yes · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Filters on string literals return fewer rows
- GROUP BY produces separate groups for 'Active' and 'ACTIVE'; joins drop rows

Detection (static_and_profile): String equality/IN/LIKE predicates, string join keys and GROUP BY on character columns; explicit *_CI_* collations; Database/column collation is case-insensitive (SQL_Latin1_General_CP1_CI_AS etc.). Detectors: `static.ms_case_insensitive`, `profile.case_insensitive_columns`.

Fix patterns:

- **FX-MS-01-A** — Programme collation policy: COLLATE 'en-ci' on affected columns *(when: Policy = case_insensitive_collation)*
- **FX-MS-01-B** — Normalise case at ingestion or compare/group on UPPER(col); test joins, filters and GROUP BY *(when: Policy = normalise_case)*

Tests: TC-MS-01-001, TC-MS-01-002, TC-MS-01-101. Validation normalisation: Case-fold string columns for L3 hashing only when policy normalise_case is applied

### MS-02 — DATETIME rounding (1/300 s, about 3 ms) vs Snowflake precision

Severity **S1** · checklist items 4 · decision required: yes · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- End-of-day boundaries ('23:59:59.999') include next-day midnight rows in SQL Server only
- L3 timestamp mismatches in the milliseconds

Detection (static_and_profile): DATETIME/SMALLDATETIME columns and variables, literals ending in .997/.998/.999, DATEADD(ms, -n, ...) boundaries; Source column type DATETIME. Detectors: `static.ms_datetime_precision`, `profile.datetime_columns`.

Fix patterns:

- **FX-MS-02-A** — Replace '.999' end-of-day literals by the value SQL Server actually used (next day 00:00:00.000) for parity, then move to half-open intervals with data-owner sign-off *(when: Report parity required during parallel run)*
- **FX-MS-02-B** — Explicit TIMESTAMP_NTZ(3) precision and L3 tolerance per rubric *(when: Reconciliation of migrated DATETIME columns)*

Tests: TC-MS-02-001, TC-MS-02-101. Validation normalisation: Truncate timestamps to milliseconds before L3 hashing when policy datetime_tolerance is applied

### MS-03 — NOLOCK and isolation hints assume the locking model

Severity **S4** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Hints fail to convert or are silently meaningless

Detection (static): WITH (NOLOCK), READUNCOMMITTED, HOLDLOCK, UPDLOCK, SET TRANSACTION ISOLATION LEVEL. Detectors: `static.ms_nolock`.

Fix patterns:

- **FX-MS-03-A** — Remove hints; Snowflake uses snapshot semantics *(when: Always)*

Tests: TC-MS-03-101. Validation normalisation: None

### MS-04 — Implicit conversions (string to number, string to date)

Severity **S1** · checklist items 9, 11 · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Date literals resolve to different days (SET DATEFORMAT dmy vs Snowflake AUTO)
- Comparisons between VARCHAR and numbers behave differently

Detection (static): SET DATEFORMAT/LANGUAGE, ambiguous dd/mm literals, comparisons mixing string and numeric operands. Detectors: `static.ms_implicit_conversion`.

Fix patterns:

- **FX-MS-04-A** — Explicit casts with format models, e.g. TO_DATE('01/10/2026', 'DD/MM/YYYY'); parser flags every implicit conversion *(when: Always)*

Tests: TC-MS-04-001. Validation normalisation: None

### MS-05 — Error handling with TRY/CATCH, @@ERROR, @@ROWCOUNT, RAISERROR

Severity **S2** · checklist items 12 · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Converted procedures do not stop or roll back as before

Detection (static): BEGIN TRY/CATCH, @@ERROR, @@ROWCOUNT, @@TRANCOUNT, RAISERROR, THROW. Detectors: `static.ms_error_handling`.

Fix patterns:

- **FX-MS-05-A** — Snowflake Scripting EXCEPTION blocks and SQLROWCOUNT *(when: Always)*

Tests: TC-MS-05-101. Validation normalisation: None

### MS-06 — Dynamic SQL built from strings

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Statically converted code still emits T-SQL at runtime

Detection (static): EXEC(@sql), EXEC @sql, sp_executesql. Detectors: `static.ms_dynamic_sql`.

Fix patterns:

- **FX-MS-06-A** — Static analysis + AI review of every generated string; EXECUTE IMMEDIATE with bind variables *(when: Always)*

Tests: TC-MS-06-101. Validation normalisation: None

### MS-07 — SSIS packages with script tasks (C#)

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Business logic hidden in script tasks is lost by automated conversion

Detection (static_and_profile): ScriptTask / ScriptComponent elements in .dtsx packages; SSISDB catalog reports packages with script tasks. Detectors: `static.ms_ssis_script_task`, `profile.ssis_script_tasks`.

Fix patterns:

- **FX-MS-07-A** — Re-engineer; never convert script tasks blindly *(when: Always)*

Tests: TC-MS-07-101. Validation normalisation: None

### MS-08 — Triggers and cascading foreign keys enforce integrity that Snowflake does not

Severity **S1** · checklist items 6 · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Orphan child rows after deletes; duplicate keys accepted on insert

Detection (static_and_profile): ON DELETE/UPDATE CASCADE, CREATE TRIGGER, PRIMARY KEY/UNIQUE/FOREIGN KEY/CHECK constraints; Enforced constraints and triggers in sys.foreign_keys / sys.triggers. Detectors: `static.constraints_enforcement`, `profile.unenforced_constraints`.

Fix patterns:

- **FX-MS-08-A** — Move cascades into pipeline logic (delete children first) and constraints into DQ rules *(when: Always)*

Tests: TC-MS-08-001, TC-MS-08-101. Validation normalisation: None

### MS-09 — Row-by-row OLTP patterns pointed at the warehouse

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- High credit burn from singleton DML

Detection (static): Cursors, FETCH NEXT, WHILE loops with singleton DML. Detectors: `static.cursor_loops`.

Fix patterns:

- **FX-MS-09-A** — Hybrid tables only for genuine OLTP-ish needs; otherwise set-based rewrite or keep OLTP elsewhere *(when: Always)*

Tests: TC-MS-09-101. Validation normalisation: None

### MS-10 — Synapse distribution and columnstore tuning emulation

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-sqlserver.

Symptoms:

- Effort spent emulating distribution with no benefit

Detection (static): DISTRIBUTION = HASH/ROUND_ROBIN/REPLICATE, CLUSTERED COLUMNSTORE INDEX, index DDL. Detectors: `static.ms_synapse_distribution`.

Fix patterns:

- **FX-MS-10-A** — Remove; measure; cluster only if needed *(when: Always)*

Tests: TC-MS-10-101. Validation normalisation: None

## netezza

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| NZ-01 | S3 | Distribution keys and zone-map design are irrelevant in Snowflake | `static.nz_distribution` | FX-NZ-01-A | 1 |
| NZ-02 | S2 | NZPLSQL stored procedures need rewriting | `static.nz_nzplsql` | FX-NZ-02-A | 1 |
| NZ-03 | S2 | nzsql shell orchestration must be rebuilt | `static.nz_shell` | FX-NZ-03-A | 1 |
| NZ-04 | S1 | Integer division returns an integer in Netezza; Snowflake returns a decimal | `static.int_division` | FX-NZ-04-A | 1 |
| NZ-05 | S1 | Date behaviours differ (day-of-week numbering, date part semantics) | `static.nz_date_behaviour` | FX-NZ-05-A | 1 |
| NZ-06 | S4 | End-of-support timelines drive deadline pressure | `profile.end_of_support` | FX-NZ-06-A | 1 |

### NZ-01 — Distribution keys and zone-map design are irrelevant in Snowflake

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Effort spent emulating DISTRIBUTE ON / ORGANIZE ON

Detection (static): DISTRIBUTE ON, ORGANIZE ON, GROOM TABLE, GENERATE STATISTICS. Detectors: `static.nz_distribution`.

Fix patterns:

- **FX-NZ-01-A** — Drop distribution/organisation clauses; cluster only when measured pruning benefit justifies it *(when: Always)*

Tests: TC-NZ-01-101. Validation normalisation: None

### NZ-02 — NZPLSQL stored procedures need rewriting

Severity **S2** · checklist items 12 · decision required: no · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Procedures fail to convert automatically

Detection (static): LANGUAGE NZPLSQL, BEGIN_PROC/END_PROC. Detectors: `static.nz_nzplsql`.

Fix patterns:

- **FX-NZ-02-A** — Rewrite in Snowflake Scripting, set-based where possible *(when: Always)*

Tests: TC-NZ-02-101. Validation normalisation: None

### NZ-03 — nzsql shell orchestration must be rebuilt

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Control flow and error handling live in shell scripts around nzsql/nzload

Detection (static): nzsql, nzload, nz_migrate invocations in shell scripts. Detectors: `static.nz_shell`.

Fix patterns:

- **FX-NZ-03-A** — Snowflake SQL + orchestrator (tasks or external) with explicit error handling; COPY INTO for nzload *(when: Always)*

Tests: TC-NZ-03-101. Validation normalisation: None

### NZ-04 — Integer division returns an integer in Netezza; Snowflake returns a decimal

Severity **S1** · checklist items 3 · decision required: no · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Ratios and averages gain decimals

Detection (static): Integer expression / integer expression. Detectors: `static.int_division`.

Fix patterns:

- **FX-NZ-04-A** — TRUNC(a / b) where integer semantics were intended; explicit NUMBER cast otherwise *(when: Always)*

Tests: TC-NZ-04-001. Validation normalisation: None

### NZ-05 — Date behaviours differ (day-of-week numbering, date part semantics)

Severity **S1** · checklist items 4, 11 · decision required: no · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Weekday buckets shifted by one (Netezza DOW Sunday=1; Snowflake DAYOFWEEK Sunday=0 with WEEK_START=0)

Detection (static): EXTRACT(DOW ...), DATE_PART('dow', ...), TO_CHAR(..., 'D'). Detectors: `static.nz_date_behaviour`.

Fix patterns:

- **FX-NZ-05-A** — DAYOFWEEK(d) + 1 (with WEEK_START = 0) or DAYOFWEEKISO per agreed calendar; set WEEK_START explicitly *(when: Always)*

Tests: TC-NZ-05-001. Validation normalisation: None

### NZ-06 — End-of-support timelines drive deadline pressure

Severity **S4** · checklist items — · decision required: yes · last verified 2026-10-01 by practice-lead-netezza.

Symptoms:

- Migration scope squeezed by appliance end of support

Detection (profile): Platform end-of-support date within rubric.patterns.profile.end_of_support_horizon_days. Detectors: `profile.end_of_support`.

Fix patterns:

- **FX-NZ-06-A** — Favour lift-and-shift + refactor backlog to meet the deadline *(when: End of support inside the horizon)*

Tests: TC-NZ-06-101. Validation normalisation: None

## redshift

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| RS-01 | S2 | Case-folding of identifiers when quoted identifiers are used | `static.quoted_identifiers` | FX-RS-01-A | 1 |
| RS-02 | S2 | VARCHAR lengths are bytes in Redshift and characters in Snowflake | `static.rs_varchar_length` | FX-RS-02-A | 1 |
| RS-03 | S2 | Late-binding views | `static.rs_late_binding_views` | FX-RS-03-A | 1 |
| RS-04 | S4 | UNLOAD patterns must be re-pointed | `static.rs_unload` | FX-RS-04-A | 1 |
| RS-05 | S3 | DISTKEY/SORTKEY/ENCODE tuning has no equivalent | `static.rs_dist_sort` | FX-RS-05-A | 1 |

### RS-01 — Case-folding of identifiers when quoted identifiers are used

Severity **S2** · checklist items 1 · decision required: yes · last verified 2026-10-01 by practice-lead-redshift.

Symptoms:

- Objects created with quoted mixed-case names are not found (Redshift folds to lower case, Snowflake to upper case)

Detection (static): Quoted identifiers containing lower-case letters; enable_case_sensitive_identifier. Detectors: `static.quoted_identifiers`.

Fix patterns:

- **FX-RS-01-A** — Identifier policy: unquote and upper-case, or quote consistently everywhere (QUOTED_IDENTIFIERS_IGNORE_CASE where agreed) *(when: Always)*

Tests: TC-RS-01-101. Validation normalisation: None

### RS-02 — VARCHAR lengths are bytes in Redshift and characters in Snowflake

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-redshift.

Symptoms:

- Length checks and fixed-width extracts differ for multibyte data

Detection (static_and_profile): VARCHAR(n)/CHAR(n) declarations; Profiled max byte length differs from max character length. Detectors: `static.rs_varchar_length`, `profile.varchar_multibyte`.

Fix patterns:

- **FX-RS-02-A** — Re-derive VARCHAR(n) in characters from profiled data; review LENGTH/OCTET_LENGTH usage *(when: Multibyte data present)*

Tests: TC-RS-02-101. Validation normalisation: None

### RS-03 — Late-binding views

Severity **S2** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-redshift.

Symptoms:

- Views reference objects that do not exist yet; deployment order breaks

Detection (static): WITH NO SCHEMA BINDING. Detectors: `static.rs_late_binding_views`.

Fix patterns:

- **FX-RS-03-A** — Deploy views in dependency order; validate references at build time *(when: Always)*

Tests: TC-RS-03-101. Validation normalisation: None

### RS-04 — UNLOAD patterns must be re-pointed

Severity **S4** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-redshift.

Symptoms:

- Downstream file consumers stop receiving extracts

Detection (static): UNLOAD ('...') TO 's3://...'. Detectors: `static.rs_unload`.

Fix patterns:

- **FX-RS-04-A** — COPY INTO @stage with explicit file format; data sharing where consumers allow *(when: Always)*

Tests: TC-RS-04-101. Validation normalisation: None

### RS-05 — DISTKEY/SORTKEY/ENCODE tuning has no equivalent

Severity **S3** · checklist items — · decision required: no · last verified 2026-10-01 by practice-lead-redshift.

Symptoms:

- Effort spent emulating distribution and sort keys

Detection (static): DISTKEY, SORTKEY, DISTSTYLE, INTERLEAVED, ENCODE. Detectors: `static.rs_dist_sort`.

Fix patterns:

- **FX-RS-05-A** — Remove; cluster only when measured pruning benefit justifies it *(when: Always)*

Tests: TC-RS-05-101. Validation normalisation: None

## common

| Id | Sev | Issue | Detector | Primary fix | Tests |
|---|---|---|---|---|---|
| XD-07 | S1 | String sort order and MIN/MAX follow a case-insensitive collation in the source | `static.string_collation_order` | FX-XD-07-A | 1 |
| XD-08 | S1 | Nondeterministic UPDATE ... FROM / MERGE with multi-match sources | `static.update_from_join` | FX-XD-08-A | 1 |
| XD-10 | S2 | Floating-point aggregation order makes exact reconciliation fail | `static.float_aggregation` | FX-XD-10-A | 1 |
| XD-12 | S2 | Transaction and commit semantics in procedures (autocommit, DDL implicit commits) | `static.transaction_semantics` | FX-XD-12-A | 1 |

### XD-07 — String sort order and MIN/MAX follow a case-insensitive collation in the source

Severity **S1** · checklist items 7 · decision required: yes · last verified 2026-10-01 by practice-lead-migration. Applies to: teradata, sqlserver.

Symptoms:

- ORDER BY returns 'Banana' before 'apple'; MIN/MAX on strings return different values

Detection (static): ORDER BY, MIN(), MAX() over character columns in sources whose default collation is case-insensitive. Detectors: `static.string_collation_order`.

Fix patterns:

- **FX-XD-07-A** — Order and aggregate on a case-folded key: ORDER BY UPPER(col), col; MIN_BY(col, UPPER(col)) / MAX_BY(col, UPPER(col)); or COLLATE 'en-ci' *(when: Source collation is case-insensitive)*

Tests: TC-XD-07-001. Validation normalisation: L4 result diffs compare ordered results; case-only diffs cluster to the collation issue

### XD-08 — Nondeterministic UPDATE ... FROM / MERGE with multi-match sources

Severity **S1** · checklist items 8 · decision required: no · last verified 2026-10-01 by practice-lead-migration. Applies to: oracle, sqlserver, netezza, redshift.

Symptoms:

- Updated values differ between runs; MERGE fails with duplicate-row errors

Detection (static): UPDATE ... FROM joins and MERGE statements whose source may be non-unique on the join key. Detectors: `static.update_from_join`, `profile.update_source_uniqueness`.

Fix patterns:

- **FX-XD-08-A** — Pre-aggregate or dedupe the source to one row per target key before UPDATE/MERGE *(when: Always for multi-match sources)*

Tests: TC-XD-08-001. Validation normalisation: None

### XD-10 — Floating-point aggregation order makes exact reconciliation fail

Severity **S2** · checklist items 10 · decision required: no · last verified 2026-10-01 by practice-lead-migration. Applies to: teradata, oracle, sqlserver, netezza, redshift.

Symptoms:

- SUM/AVG over FLOAT columns differ in the last digits between engines and between runs

Detection (static): FLOAT/REAL/DOUBLE/BINARY_DOUBLE columns or casts that feed SUM/AVG. Detectors: `static.float_aggregation`.

Fix patterns:

- **FX-XD-10-A** — Use NUMBER(p,s) for monetary/exact measures; reconcile FLOAT aggregates with rubric.validation.thresholds.*.l2_float_rel_tolerance *(when: Always)*

Tests: TC-XD-10-101. Validation normalisation: Relative tolerance for FLOAT aggregates in L2 (rubric)

### XD-12 — Transaction and commit semantics in procedures (autocommit, DDL implicit commits)

Severity **S2** · checklist items 12 · decision required: no · last verified 2026-10-01 by practice-lead-migration. Applies to: teradata, oracle, sqlserver, netezza, redshift.

Symptoms:

- Partial results persist after failures; DDL inside a transaction commits earlier work

Detection (static): BEGIN TRAN/BT, COMMIT/ET, ROLLBACK, SET IMPLICIT_TRANSACTIONS, DDL inside procedure bodies. Detectors: `static.transaction_semantics`.

Fix patterns:

- **FX-XD-12-A** — Explicit BEGIN/COMMIT in Snowflake Scripting; move DDL out of transactional units (DDL commits implicitly) *(when: Always)*

Tests: TC-XD-12-101. Validation normalisation: None
