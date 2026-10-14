# Contributing — engineering conventions

These conventions are CI-enforced (see `.github/workflows/ci.yml`, run locally with `make check`).

## Layout

| Path | What lives there |
|---|---|
| `services/altitude/core/` | rubric refs, knowledge validator, canonical store, snapshots, AI records/review queue, generated-file stamping, theme tokens, audit |
| `services/altitude/<module>/` | one platform service per directory (diagnostics, observability, patterns, validation, assessment, planning, conversion, etl, foundation, airready, api, mcp, ...) |
| `connectors/altitude_connectors/` | read-only source connectors + extraction agent |
| `agents/altitude_agents/` | agent fleet runtime and agents |
| `knowledge/` | **all** mappings, known issues, checks, KPIs, rubrics, playbooks, prompts — versioned YAML |
| `generated/` | header-stamped renderings; never edit by hand; `altitude generate` |
| `portal/` | static portal assets (templates use theme tokens only) |
| `skills/` | executable skill manifests exposed via API/MCP |
| `tests/<module>/` | tests per module; shared fixtures in `tests/conftest.py` |

## Rules

1. **No thresholds in code.** Numeric thresholds, weights and factors live in `knowledge/rubrics/<namespace>.yaml`
   and are read with `RubricSet.get("rubric.<namespace>.<path>")`. `tools/lint_thresholds.py` flags numeric
   comparisons (other than 0/1/-1) and threshold-like names bound to literals. Unavoidable non-threshold literals
   need `# threshold-ok: <reason>`.
2. **Knowledge files are schema-governed.** Each YAML file under `knowledge/` must match exactly one JSON schema in
   `services/altitude/core/schemas/*.json` via its `x-altitude-globs`. IDs are unique across the knowledge base.
   Fields ending `threshold_ref` must be `rubric.*` references and every reference must resolve.
3. **Every AI output carries confidence + rationale** (`altitude.core.ai.Inference`); below
   `rubric.ai.review_confidence_min` it goes to the review queue (`ReviewQueue`) and has no effect until approved.
   The default provider is the offline, deterministic `TemplateProvider`.
4. **Human approval before promotion.** Nothing reaches production without a recorded approver (`approval`/`review`).
5. **Snapshots are immutable.** Computations read sealed `Snapshot`s and record `snapshot_id` + `rubric_version`;
   same inputs ⇒ byte-identical outputs (no wall-clock or random values in computed results).
6. **Source is never modified.** Connectors are read-only with a published permission manifest and a kill-test.
7. **Generated files** are produced by `altitude.<module>.generate.generate() -> {relpath: content}` (paths under
   `generated/<module>/`), stamped with `altitude.core.generated.stamp`, and committed.
8. **White-label.** User-facing templates live in `templates/` directories and use `{{PRODUCT_NAME}}`-style tokens
   rendered by `altitude.core.theme.render`; no raw brand names or hex colours there.
9. **Migrations**: PostgreSQL dialect in `services/altitude/core/migrations/NNNN_<module>.sql`
   (0001–0099 core, 0100 diagnostics, 0200 patterns/validation, 0300 observability, 0400 agents/foundation/airready,
   0500 connectors/assessment/planning, 0600 conversion/etl, 0700 api/portal). Must transpile to DuckDB via sqlglot.
10. **Harvest contract.** Snowflake evidence tables and columns are defined once in
    `altitude.synthetic.schema.HARVEST_SCHEMA`; live harvest and the synthetic estate both produce exactly these.
