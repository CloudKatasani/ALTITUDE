# BUILD.md — milestone status (Section 38)

Build order followed: M0 → M1 → MD → MO → M7 → M10 → M2–M6 → M8, M9, M11, M12.
CI (`.github/workflows/ci.yml`, locally `make check`) runs on every change: knowledge validation, threshold lint,
de-branding lint, generated-artifact diff, and the full test suite.

| Milestone | Status | Acceptance criterion → proving test |
|---|---|---|
| **M0** Repository & canonical model | ✅ | Malformed knowledge YAML fails with a precise `file:line: $.path` error → `tests/core/test_rubric_knowledge.py`; numeric literals in threshold positions fail CI → `tests/core/test_ai_lints_generated.py::test_threshold_lint_flags_literals`; append-only kill-test → `tests/core/test_store_snapshot.py` |
| **M1** Pattern Library v0 | ✅ | Each S1 issue has an executable detector and a passing golden test on synthetic data → `tests/patterns/test_patterns_golden.py` |
| **MD** Diagnostics engine (Package D) | ✅ | Same snapshot + rubric ⇒ identical scores/values/exports; every suggestion has evidence refs, value method, confidence, rollback; no ACCOUNTADMIN; ≥90% recall ≤10% FP on seeded estate (actual: 100% / 0%) → `tests/diagnostics/test_reproducibility_scorecard.py`, `test_engine.py`, `test_bootstrap.py`, `test_lifecycle.py` |
| **MO** Observability pack (Package O) | ✅ | History retained beyond source retention; cost KPIs reconcile to billing; seeded anomaly fires the right alert; agent answers golden questions with citations → `tests/observability/test_obs_harvest.py`, `test_kpis.py`, `test_alerts.py`, `test_agent.py`, `test_raw_immutability.py`, `test_value.py` |
| **M2** Extraction agent & harvest | ✅ | Kill-test proves no write capability; harvest populates objects, dependencies, usage; no row data shipped → `tests/connectors/test_connectors_killtest.py`, `test_connectors_harvest.py` |
| **M3** Assessment engine | ✅ | Same snapshot + rubric ⇒ identical scores; low-confidence items in review queue → `tests/assessment/test_assessment_engine.py` |
| **M4** Planning & estimation | ✅ | Estimates reference the rubric version and reproduce; wave plan respects gate/wave rules as data → `tests/planning/` |
| **M5** Conversion orchestrator | ✅ | No artifact promotable without review; every AI change has confidence, rationale, model and prompt version → `tests/conversion/test_workflow.py` |
| **M6** Validation engine | ✅ | TD-01, TD-02, OR-01, MS-01 drift detected and clustered to the right known issue → `tests/validation/test_validation_acceptance.py` |
| **M7** Foundation accelerators | ✅ (structural) | Terraform generated from the YAML model and linted structurally (no `terraform` binary / trial account in CI); WA checker reports findings with playbooks → `tests/foundation/` |
| **M8** Portal & Sherpa | ✅ | Every board number links to evidence/suggestion IDs; Sherpa cites evidence and refuses when ungrounded → `tests/e2e/test_flagship_flow.py`, `tests/advisory/test_advisory.py`, `tests/api/` |
| **M9** ETL & scheduler converters | ✅ | Sample SSIS/Informatica packages produce dbt projects that compile and pass generated tests on synthetic data (DuckDB harness); scheduler DAGs valid → `tests/etl/` |
| **M10** Agent fleet v1 | ✅ | L2 never executes without approval; L3 limited to the pre-approved catalogue with auto-rollback → `tests/agents/test_autonomy.py`, `test_action_log.py`, `test_evals.py` |
| **M11** AI-Ready module | ✅ | Readiness score reproducible per snapshot; semantic views from the KPI registry with one definition per KPI (also enforced by `altitude knowledge validate`) → `tests/airready/`, `tests/core/test_semantic_hook.py` |
| **M12** Editions, MCP & packaging | ✅ | De-branding lint passes and a partner theme re-brands every page; exported deck, PDF and dashboard read the same snapshot (shared numbers hash); MCP protocol and RBAC → `tests/api/test_api_core.py::test_white_label_partner_theme_is_configuration_only`, `tests/packaging/`, `tests/mcp/` |

Also built beyond the milestone list: cutover & decommissioning (§13, `tests/cutover/`), data movement planning (§12,
`tests/movement/`), commercials and guarantees (§5–6, §34, `tests/commercial/`), peer benchmarks and buying signals
(§4.6, §2, `tests/benchmark_gtm/`).

## Not verifiable in this environment

- Execution against a live Snowflake account (harvest SQL, Native App setup script, generated DDL, Cortex objects).
- `terraform validate/apply` against a trial account (M7's second acceptance clause).
- The real SnowConvert AI CLI (tested against a fake CLI with the documented report format).

These are syntax- and structure-checked in CI and are the first items to run on a design-partner account.
