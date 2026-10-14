<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/validation/normalisation.yaml, knowledge/validation/triage_signatures.yaml. Regenerate with `altitude generate`. -->
# Normalisation rules

Version 1.0.0. Applied identically on both sides before L2 aggregation and L3 hashing. `always` rules only canonicalise representation; policy rules are enabled per programme ADR.

| Rule | Operation | Applies to | When | Linked issues | Description |
|---|---|---|---|---|---|
| NR-CANON-NUMERIC | `numeric_canonical` | integer, decimal | always | — | Render exact numerics as canonical decimals (no trailing zeros) so 1.50 and 1.5 hash identically |
| NR-CANON-FLOAT | `float_canonical` {'significant_digits': 15} | float | always | — | Render floats with 15 significant digits so engine-specific last-digit noise does not mismatch |
| NR-CANON-TIMESTAMP | `timestamp_canonical` | timestamp | always | — | Render timestamps as ISO-8601 with microseconds |
| NR-CANON-DATE | `date_canonical` | date | always | — | Render dates as ISO-8601 |
| NR-CANON-BOOLEAN | `boolean_canonical` | boolean | always | — | Render booleans as true/false |
| NR-RTRIM | `rtrim` | string | policy `char_padding_ignored` | TD-03 | Remove trailing spaces (CHAR pad semantics) |
| NR-CASEFOLD | `upper` | string | policy `normalise_case` | TD-02, MS-01, XD-07 | Compare strings case-insensitively |
| NR-EMPTY-AS-NULL | `empty_as_null` | string | policy `oracle_null_semantics` | OR-01 | Treat '' and NULL as equal |
| NR-TS-MILLIS | `timestamp_precision` {'fractional_digits': 3} | timestamp | policy `datetime_tolerance` | MS-02, TD-11 | Truncate timestamps to milliseconds |
| NR-NUMERIC-SCALE | `numeric_scale` {'scale': 2} | decimal | policy `aligned_numeric_scale` | OR-02 | Round exact numerics to the agreed reporting scale (only after the scale ADR is signed) |

## Triage signatures

| Signature | Description | Known issue by source dialect |
|---|---|---|
| `duplicate_rows` | Target holds extra copies of rows that are otherwise identical to the source row | sqlserver→MS-08, teradata→TD-01 |
| `trailing_space` | Values differ only by trailing spaces | teradata→TD-03 |
| `case_only` | Values differ only by letter case | sqlserver→MS-01, teradata→TD-02 |
| `empty_vs_null` | One side holds '' where the other holds NULL | oracle→OR-01 |
| `scale_truncation` | Target numeric equals the source rounded/truncated to fewer decimal places | netezza→NZ-04, oracle→OR-02, teradata→TD-05 |
| `timestamp_precision` | Timestamps differ by less than a second (fractional precision or DATETIME rounding) | sqlserver→MS-02, teradata→TD-11 |
| `time_component_lost` | Target keeps the date but the time of day is midnight | oracle→OR-03 |
| `timezone_shift` | Timestamps differ by a whole number of hours | teradata→TD-11 |
| `float_precision` | Floating-point values differ only in the last significant digits | netezza→XD-10, oracle→XD-10, redshift→XD-10, sqlserver→XD-10, teradata→XD-10 |
| `missing_rows` | Keys present in the source are missing in the target | — (human triage) |
| `extra_rows` | Keys present in the target are missing in the source | sqlserver→MS-08 |
| `unexplained` | No known signature explains the difference; human triage required | — (human triage) |
