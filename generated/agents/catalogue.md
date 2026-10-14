<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/agents/catalogue.yaml, knowledge/agents/action_catalogue.yaml. Regenerate with `altitude generate`. -->
# Agent fleet catalogue

| # | Agent | Trigger | Max autonomy | Guardrails | KPI | Tools | Identity | Status |
|---|---|---|---|---|---|---|---|---|
| 1 | Cost Sentinel | Hourly | L1 | read_only | Forecast error; anomalies caught before invoice | daily_credits, warehouse_daily_credits, signature_credits | SVC_ALT_COST_SENTINEL / ALT_AGENT_COST_SENTINEL | v1 1.0.0 |
| 2 | Warehouse Rightsizer | Daily | L3 | change_window, auto_revert_on_queueing | Credits saved; SLA breaches = 0 | warehouse_config, warehouse_utilisation, warehouse_load, warehouse_query_profile | SVC_ALT_RIGHTSIZER / ALT_AGENT_RIGHTSIZER | v1 1.0.0 |
| 3 | Query Performance Doctor | On regression | L2 | test_on_clone_before_proposing | p95 runtime trend | signature_runtime_trend, table_pruning_profile | SVC_ALT_QUERY_DOCTOR / ALT_AGENT_QUERY_DOCTOR | planned |
| 4 | Pipeline Triage | Task/dbt failure | L3 | idempotency_flag_as_data | MTTR | task_failures, task_definitions, task_idempotency, recent_ddl | SVC_ALT_PIPELINE_TRIAGE / ALT_AGENT_PIPELINE_TRIAGE | v1 1.0.0 |
| 5 | Schema Drift Guard | Source change | L2 | contract_rules | Breaks prevented | column_changes, table_lineage | SVC_ALT_SCHEMA_DRIFT / ALT_AGENT_SCHEMA_DRIFT | planned |
| 6 | DQ Incident Agent | DMF/rule failure | L2 | never_deletes_data | Detection lead time vs consumer discovery | dq_violations, table_lineage, task_failures, load_errors, recent_ddl, table_owners, tier1_tables | SVC_ALT_DQ_INCIDENT / ALT_AGENT_DQ_INCIDENT | v1 1.0.0 |
| 7 | Access Hygiene Agent | Weekly | L2 | owner_approval_required | Dormant grants; review completion | users, user_role_grants, role_grants, roles, privileged_usage | SVC_ALT_ACCESS_HYGIENE / ALT_AGENT_ACCESS_HYGIENE | v1 1.0.0 |
| 8 | Security Posture Agent | Daily | L1 | escalates_to_soc | Open critical findings | users, login_anomalies, network_policies | SVC_ALT_SECURITY_POSTURE / ALT_AGENT_SECURITY_POSTURE | planned |
| 9 | Storage & Object Pruner | Weekly | L2 | archive_before_drop, legal_hold_check | Storage TB/cost reduced | table_storage, table_access_recency | SVC_ALT_STORAGE_PRUNER / ALT_AGENT_STORAGE_PRUNER | planned |
| 10 | Release Change Watcher | On new behaviour-change bundle / release notes | L1 | — | Upgrade incidents = 0 | usage_signature_scan | SVC_ALT_RELEASE_WATCHER / ALT_AGENT_RELEASE_WATCHER | v1 1.0.0 |
| 11 | Documentation & Catalog Agent | On object create/change | L2 | steward_approval | Description coverage on Tier-1 | column_metadata, tier1_tables | SVC_ALT_DOC_CATALOG / ALT_AGENT_DOC_CATALOG | planned |
| 12 | Classification Agent | On new columns | L2 | privacy_approval | Unprotected classified columns = 0 | column_metadata, column_tags, masking_policies | SVC_ALT_CLASSIFICATION / ALT_AGENT_CLASSIFICATION | planned |
| 13 | Lineage Gap Agent | Weekly | L1 | — | Lineage coverage % | table_lineage, tier1_tables | SVC_ALT_LINEAGE_GAP / ALT_AGENT_LINEAGE_GAP | planned |
| 14 | SLA Forecaster | Continuous | L1 | — | Late deliveries warned | task_timings, freshness_slas | SVC_ALT_SLA_FORECASTER / ALT_AGENT_SLA_FORECASTER | planned |
| 15 | Cortex Cost & Quality Monitor | Daily | L1 | — | Cost per accepted answer | cortex_usage | SVC_ALT_CORTEX_MONITOR / ALT_AGENT_CORTEX_MONITOR | planned |
| 16 | Semantic Model Steward | On dbt/KPI change | L2 | owner_approval_required | KPI definition conflicts | bi_measures, semantic_views | SVC_ALT_SEMANTIC_STEWARD / ALT_AGENT_SEMANTIC_STEWARD | planned |

## Pre-approved action catalogue (L3)

| Entry | Tenants | Action | Agents | Scope | Rollback | Guard |
|---|---|---|---|---|---|---|
| PA-DEFAULT-WH-AUTO-SUSPEND | * | warehouse.set_auto_suspend | AG-WAREHOUSE-RIGHTSIZER | WH_* excl. WH_ELT_* | automatic | warehouse_queued_load |
| PA-DEFAULT-TASK-RERUN | * | task.rerun | AG-PIPELINE-TRIAGE | *.*.* excl. — | none_idempotent | — |

## Action types

| Action | Object | SQL | Rollback | Executable |
|---|---|---|---|---|
| warehouse.set_auto_suspend | warehouse | `ALTER WAREHOUSE {target} SET AUTO_SUSPEND = {auto_suspend}` | `ALTER WAREHOUSE {target} SET AUTO_SUSPEND = {previous.auto_suspend}` | yes |
| warehouse.resize | warehouse | `ALTER WAREHOUSE {target} SET WAREHOUSE_SIZE = '{warehouse_size}'` | `ALTER WAREHOUSE {target} SET WAREHOUSE_SIZE = '{previous.warehouse_size}'` | yes |
| warehouse.set_max_cluster_count | warehouse | `ALTER WAREHOUSE {target} SET MAX_CLUSTER_COUNT = {max_cluster_count}` | `ALTER WAREHOUSE {target} SET MAX_CLUSTER_COUNT = {previous.max_cluster_count}` | yes |
| task.rerun | task | `EXECUTE TASK {target}` | `—` | yes |
| task.fix_draft | task | `(draft only)` | `—` | no (PR) |
| user.disable | user | `ALTER USER {target} SET DISABLED = TRUE` | `ALTER USER {target} SET DISABLED = {previous.disabled}` | yes |
| user.set_authentication_policy | user | `ALTER USER {target} SET AUTHENTICATION POLICY {policy}` | `ALTER USER {target} UNSET AUTHENTICATION POLICY` | yes |
| grant.revoke_role_from_user | user | `REVOKE ROLE {role} FROM USER {target}` | `GRANT ROLE {role} TO USER {target}` | yes |
| grant.revoke_privilege_from_role | role | `REVOKE {privilege} ON {object_type} {object_name} FROM ROLE {target}` | `GRANT {privilege} ON {object_type} {object_name} TO ROLE {target}` | yes |
| table.quarantine | table | `ALTER TABLE {target} SET TAG {tag} = 'QUARANTINED'` | `ALTER TABLE {target} UNSET TAG {tag}` | yes |
