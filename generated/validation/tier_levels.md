<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/validation/levels.yaml, knowledge/rubrics/validation.yaml. Regenerate with `altitude generate`. -->
# Validation levels by table tier

Levels version 1.0.0. Modes: full · sample · none (Section 12.3).

| Level | Check | tier1 | tier2 | tier3 |
|---|---|---|---|---|
| L0 | Schema parity: Columns, type families, scale and nullability, mapped per conversion rules | full | full | full |
| L1 | Row counts: Overall and per partition/date | full | full | full |
| L2 | Column aggregates: Sum, min, max, count distinct, null count and string-length stats on normalised values | full | full | sample |
| L3 | Row-level hash comparison: Keyed, normalised per drift rules; mismatch keys stay in-boundary | full | sample | none |
| L4 | Business-output parity: Report/KPI values and query-result diffs on top production queries | full | full | none |
| L5 | Performance parity: Top queries p50/p95 vs baseline and SLA | full | full | none |

## Thresholds (rubric)

- **tier1** (`rubric.validation.thresholds.tier1`): l0_type_mismatch_max=0, l1_count_delta_max=0, l2_float_rel_tolerance=1e-09, l2_numeric_rel_tolerance=0.0, l3_mismatch_max=0, l3_mismatch_rate_max=0.0, l4_diff_rows_max=0, l4_numeric_rel_tolerance=0.0, l5_p50_ratio_max=1.2, l5_p95_ratio_max=1.2
- **tier2** (`rubric.validation.thresholds.tier2`): l0_type_mismatch_max=0, l1_count_delta_max=0, l2_float_rel_tolerance=1e-06, l2_numeric_rel_tolerance=1e-09, l3_mismatch_max=0, l3_mismatch_rate_max=0.0, l4_diff_rows_max=0, l4_numeric_rel_tolerance=1e-09, l5_p50_ratio_max=1.5, l5_p95_ratio_max=1.5
- **tier3** (`rubric.validation.thresholds.tier3`): l0_type_mismatch_max=0, l1_count_delta_max=0, l2_float_rel_tolerance=1e-06, l2_numeric_rel_tolerance=1e-06, l3_mismatch_max=0, l3_mismatch_rate_max=0.0, l4_diff_rows_max=0, l4_numeric_rel_tolerance=1e-06, l5_p50_ratio_max=2.0, l5_p95_ratio_max=2.0

Sampling: L3 sample rate `rubric.validation.sampling.l3_sample_rate` = 0.1; L2 sample partitions `rubric.validation.sampling.l2_sample_partitions` = 3.
