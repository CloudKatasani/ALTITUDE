# ALTITUDE — evidence-first Snowflake diagnostics, observability, migration and run platform

Implementation of `ALTITUDE_Snowflake_Partner_Platform_Spec_v1.1.md`. `ALTITUDE` is a working codename:
every user-facing name and colour is a theme token (`knowledge/theme/*.yaml`), so a partner edition is configuration only.

**What it does.** It diagnoses a Snowflake estate down to the dollar (Package D), keeps it observable in the client's
own account (Package O), operates it with governed agents, and migrates legacy warehouses with provable equivalence.
Every finding traces back to evidence in an immutable snapshot, every threshold is data, and every AI output carries
confidence and a rationale and waits for a human when it should.

## Quick start

```bash
make install                       # venv + editable install
make check                         # knowledge validate, lints, generated-diff check, full test suite
make site                          # public website as static HTML in out/site (samples from the synthetic estate)
make demo                          # live server + full flow through the API; screenshots in out/demo/screenshots
make demo-serve                    # same, then leave the portal running on :8099

# A synthetic estate with 33 seeded issue types (or --profile clean)
.venv/bin/altitude synthetic snapshot --out .altitude/snapshots --ground-truth gt.json
.venv/bin/altitude diag run --snapshot .altitude/snapshots/SNAP-ACME-2026-09-30-SEEDED.duckdb --out out/diag
.venv/bin/altitude patterns scan --dialect teradata my_script.sql      # open-source drift checker
ALTITUDE_AUTH=dev .venv/bin/altitude serve                              # website on / , portal on /app, API on /api/v1
.venv/bin/altitude mcp                                                  # MCP server (stdio) for AI clients
```

`altitude --help` lists every command group: `knowledge`, `generate`, `rubric`, `synthetic`, `diag`, `obs`,
`patterns`, `validation`, `knowledge-publish`, `agents`, `foundation`, `airready`, `connectors`, `assess`, `plan`,
`conversion`, `etl`, `serve`, `mcp`, `skills`.

## Architecture

| Layer | Where | Notes |
|---|---|---|
| Website | `services/altitude/website/`, `knowledge/website/` | Public startup site at `/`: every offering from the service catalogue, live samples computed from the synthetic estate, contact form recorded as a buying signal; static export via `altitude site build` |
| Experience | `services/altitude/api/portal.py`, `portal/` | Server-rendered client portal at `/app`: guided outcome path, engagement facts form, findings with evidence drill-through, progress board (identified vs realised), review queue, Sherpa, review board, agent approvals, dashboards |
| Access | `services/altitude/api/`, `services/altitude/mcp/`, `skills/` | REST `/api/v1`, RBAC as data (6 roles), OIDC RS256/JWKS and HS256 tokens; MCP server and REST share one skills registry |
| Services | `services/altitude/<module>/`, `agents/`, `connectors/` | see below |
| Knowledge | `knowledge/` | 136 schema-governed YAML files: checks, KPIs, known issues, mappings, rubrics, gates, playbooks, prompts |
| Data | `services/altitude/core/store.py`, `migrations/` | Canonical model in PostgreSQL DDL, transpiled to DuckDB for local/CI; append-only tables guarded in code and by PG triggers |

### Modules

| Spec | Module | Highlights |
|---|---|---|
| M0 | `altitude.core` | rubric refs, knowledge validator (file:line errors), sealed content-addressed snapshots, AI inference records + review queue, safe rule evaluator, generated-file stamping, theme tokens, audit |
| M1 | `altitude.patterns` | 47 known issues (TD/OR/MS/NZ/RS/XD), 50 mappings, executable detectors, golden tests on emulated source semantics, `scan_sql` drift checker |
| MD | `altitude.diagnostics` | 33 checks across 10 domains, suggestion engine (clustering, value model, remediation + rollback, narrative), scorecard + Platform Health Index, least-privilege bootstrap, live harvester, CSV/XLSX/Jira/ADO/PR-pack/PPTX/HTML exports |
| MO | `altitude.observability` | config-driven multi-account harvest, immutable RAW archive, 82-KPI catalogue, billing reconciliation, alerts + runbooks + routing, ask-the-platform agent with citations, suggestion-to-value loop, dashboards + chargeback, Snowflake DDL |
| M2 | `altitude_connectors` | read-only connection wrapper (kill-tested), permission manifests, SQL Server / Oracle / Teradata harvesters, metadata-only extraction agent |
| M3 | `altitude.assessment` | disposition (keep/retire/rewrite) with confidence, complexity, anti-patterns, drift-risk scan |
| M4 | `altitude.planning` | dependency-cluster waves under wave rules as data, factory state machine, pattern recommender, estimation (p50/p80), gates |
| M5 | `altitude.conversion` | SnowConvert AI CLI wrapper + report parser, sqlglot fallback, AI remediation PR packs, review/promotion gate |
| M6 | `altitude.validation` | L0–L5 suites by tier, normalisation as data, in-boundary execution, mismatch triage to known issues, accepted deviations |
| M7 | `altitude.foundation` | landing-zone YAML → Terraform, Terraform linter, 31 Well-Architected checks + playbooks |
| M8 | `altitude.api`, `altitude.advisory` | portal and boards; Sherpa (grounded, cites evidence, refuses when ungrounded, challenges risky plans), 10 specialist advisors, 7-lens review board with dissent |
| M9 | `altitude.etl` | SSIS / Informatica parsers → mapping graph → dbt project (compiled and tested in DuckDB); Control-M / SQL Agent → task graph + Airflow |
| M10 | `altitude_agents` | 16-agent catalogue, 6 implemented; L0–L3 autonomy, approvals, pre-approved catalogue with blast radius, auto-rollback, eval-gated promotion |
| M11 | `altitude.airready` | EAIRN 8-pillar score, KPI registry (one definition per KPI) → semantic views, Cortex templates + eval harness |
| M12 | `altitude.packaging`, `altitude.mcp`, `altitude.skills` | Native App bundle (in-account D0), board pack (PPTX/PDF/HTML from one snapshot), MCP server, white-label tokens |
| §26–27 | `altitude.marketplace` | data product and marketplace-agent manifests; evidence-based certification (contract, owner, docs, DMFs, masking, freshness); secure views, shares, organization listings and Cortex Agent specs; publishing emits SQL only for certified items |
| §13 | `altitude.cutover` | go/no-go evidence pack, human decision with override reason, decommission blocking, savings realisation |
| §12 | `altitude.movement` | volume-band load plans, landing DDL with lineage columns, CDC selection, restartable checkpoints |
| §5–6, 34 | `altitude.commercial` | offer catalogue, fee credit / value floor guarantees, SOW and business-case drafts |
| §4.6, §2 | `altitude.benchmark`, `altitude.gtm` | consent-gated peer benchmarks with minimum cohort; buying-signal scoring and plays |

### Design principles (CI-enforced)

See `CONTRIBUTING.md`. In short: no thresholds in code (`tools/lint_thresholds.py`), schema-validated knowledge,
confidence + rationale on every AI output with a human review floor, human approval before promotion, immutable
snapshots and append-only logs, read-only connectors with kill-tests, header-stamped generated files with a
regeneration diff check, and a de-branding lint.

## Synthetic estate and the harvest contract

`altitude.synthetic.schema.HARVEST_SCHEMA` defines exactly which evidence tables/columns a diagnostic snapshot
holds. The live harvester (`altitude.diagnostics.harvest`) and the synthetic estate produce the same layout, so every
detector, KPI, agent and score runs unchanged on either. The seeded profile carries ground truth for all 33 catalogue
checks; Package D detects all of them with no false positives, and finds nothing on the clean profile.

## Known limitations

- No live Snowflake account was available: generated Snowflake SQL, the Native App bundle, Terraform, semantic views
  and Cortex specs are syntax-checked (sqlglot / structural linters) but not executed against Snowflake. View and
  column names should be re-verified per engagement, as the spec requires.
- SnowConvert AI is integrated through its CLI and report format; tests use a fake CLI.
- The spec's reference stack names Next.js and Temporal; this implementation uses a server-rendered FastAPI/Jinja
  portal and in-process workflows with append-only state. Both are replaceable behind the same API.
- Estimation factors, prices and many rubric values are seed hypotheses awaiting calibration (the spec says the same).

See `BUILD.md` for milestone status and the test that proves each acceptance criterion.
