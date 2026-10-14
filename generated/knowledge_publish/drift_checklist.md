<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/dialects/*/known_issues.yaml. Regenerate with `altitude generate`. -->
# Cross-source semantic-drift checklist (Section 10.13)

Known issues with an executable detector per checklist item and source dialect. Run `altitude patterns scan --dialect <d> <files>` to check code against it.

| # | Checklist item | teradata | oracle | sqlserver | netezza | redshift |
|---|---|---|---|---|---|---|
| 1 | Case sensitivity (identifiers and data) | TD-02 | — | MS-01 | — | RS-01 |
| 2 | NULL vs empty string | — | OR-01 | — | — | — |
| 3 | Numeric precision/scale and integer division | TD-05 | OR-02 | — | NZ-04 | — |
| 4 | Date vs timestamp; time-zone policy (NTZ/LTZ/TZ) | TD-04, TD-11 | OR-03 | MS-02 | NZ-05 | — |
| 5 | Trailing spaces / CHAR padding | TD-03 | — | — | — | — |
| 6 | Duplicate handling (SET tables, unenforced constraints) | TD-01 | OR-07 | MS-08 | — | — |
| 7 | Sort order / collation in ORDER BY, MIN/MAX on strings | TD-02, XD-07 | OR-08 | MS-01, XD-07 | — | — |
| 8 | Nondeterministic UPDATE...FROM / MERGE with multi-match sources | TD-08 | XD-08 | XD-08 | XD-08 | XD-08 |
| 9 | Implicit casts | TD-04 | — | MS-04 | — | — |
| 10 | Floating-point aggregation order | XD-10 | XD-10 | XD-10 | XD-10 | XD-10 |
| 11 | Session parameters (date formats, week start, TIMESTAMP_TYPE_MAPPING) | TD-11 | OR-08 | MS-04 | NZ-05 | — |
| 12 | Transaction/commit semantics in procedures (autocommit, DDL implicit commits) | TD-06, XD-12 | OR-04, XD-12 | MS-05, XD-12 | NZ-02, XD-12 | XD-12 |
