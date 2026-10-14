<!-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/observability/kpis. Regenerate with `altitude generate`. -->
# Package O KPI catalogue

82 KPIs; 65 implemented, 23 in the core tier. Source: knowledge/observability/kpis.

| ID | Name | Domain | Tier | Status | Unit | Grain | Sources |
|---|---|---|---|---|---|---|---|
| KPI-AI-001 | Cortex credits by function and agent | ai | core | implemented | credits | account, function, agent, day | CORTEX_USAGE_HISTORY |
| KPI-AI-002 | Cost per accepted answer | ai | extended | planned | usd | account, agent, day | CORTEX_USAGE_HISTORY |
| KPI-AI-003 | Cortex tokens by model | ai | extended | implemented | tokens | account, model, day | CORTEX_USAGE_HISTORY |
| KPI-AI-004 | Cortex spend without agent identity | ai | extended | implemented | ratio | account, day | CORTEX_USAGE_HISTORY |
| KPI-AI-005 | Cortex call latency | ai | extended | implemented | seconds | account, function, day | CORTEX_USAGE_HISTORY |
| KPI-AI-006 | Semantic views | ai | extended | implemented | views | account, day | SEMANTIC_VIEWS |
| KPI-AI-007 | Agent evaluation drift | ai | advanced | planned | ratio | account, agent, day |  |
| KPI-AI-008 | Agent warehouse credits | ai | extended | planned | credits | account, agent, day | QUERY_ATTRIBUTION_HISTORY |
| KPI-COST-001 | Credits by account, warehouse and day | cost | core | implemented | credits | account, warehouse, day | WAREHOUSE_METERING_HISTORY, METERING_DAILY_HISTORY |
| KPI-COST-002 | Spend ($) by warehouse and day | cost | core | implemented | usd | account, warehouse, day | WAREHOUSE_METERING_HISTORY, METERING_DAILY_HISTORY, CLIENT_INPUTS |
| KPI-COST-003 | Cost by cost centre | cost | core | implemented | usd | account, cost_centre, day | WAREHOUSE_METERING_HISTORY, METERING_DAILY_HISTORY, TAG_REFERENCES, CLIENT_INPUTS |
| KPI-COST-004 | Month-on-month spend trend | cost | core | implemented | percent | account, month | METERING_DAILY_HISTORY, CLIENT_INPUTS |
| KPI-COST-005 | Forecast vs budget | cost | core | implemented | ratio | account, month | METERING_DAILY_HISTORY, BUDGETS |
| KPI-COST-006 | Cost per query signature | cost | extended | implemented | usd | account, query_signature, day | QUERY_ATTRIBUTION_HISTORY, QUERY_HISTORY, CLIENT_INPUTS |
| KPI-COST-007 | Idle credit share | cost | extended | implemented | ratio | account, warehouse, day | WAREHOUSE_METERING_HISTORY, QUERY_ATTRIBUTION_HISTORY |
| KPI-COST-008 | Serverless credit breakdown | cost | extended | implemented | credits | account, service_type, day | AUTOMATIC_CLUSTERING_HISTORY, SEARCH_OPTIMIZATION_HISTORY, MATERIALIZED_VIEW_REFRESH_HISTORY, PIPE_USAGE_HISTORY, CORTEX_USAGE_HISTORY |
| KPI-COST-009 | Storage by type | cost | extended | implemented | tb | account, storage_type, day | STORAGE_USAGE |
| KPI-COST-010 | Credits billed by service type and day | cost | core | implemented | credits | account, service_type, day | METERING_DAILY_HISTORY |
| KPI-COST-011 | Total spend ($) by account and day | cost | core | implemented | usd | account, day | METERING_DAILY_HISTORY, CLIENT_INPUTS |
| KPI-COST-012 | Storage cost per month | cost | extended | implemented | usd | account, month | STORAGE_USAGE, CLIENT_INPUTS |
| KPI-COST-013 | Capacity commitment burn-down | cost | advanced | implemented | ratio | account, day | METERING_DAILY_HISTORY, CLIENT_INPUTS |
| KPI-COST-015 | Cloud services ratio | cost | extended | implemented | ratio | account, day | METERING_DAILY_HISTORY |
| KPI-COST-016 | Unit cost per dashboard view | cost | advanced | planned | usd | account, report, month | BI_REPORTS, QUERY_ATTRIBUTION_HISTORY |
| KPI-COST-017 | Unit cost per data product | cost | advanced | planned | usd | account, data_product, month | QUERY_ATTRIBUTION_HISTORY, TABLE_STORAGE_METRICS, TAG_REFERENCES |
| KPI-COST-018 | Cost per agent answer | cost | advanced | planned | usd | account, agent, day | CORTEX_USAGE_HISTORY, QUERY_ATTRIBUTION_HISTORY |
| KPI-COST-019 | Credits by role | cost | extended | planned | credits | account, role, day | QUERY_ATTRIBUTION_HISTORY, QUERY_HISTORY |
| KPI-COST-020 | Resource monitor coverage | cost | extended | implemented | ratio | account, day | WAREHOUSES |
| KPI-GOV-001 | Tag coverage | governance | core | implemented | ratio | account, day | TABLES, TAG_REFERENCES |
| KPI-GOV-002 | Owner coverage on Tier-1 objects | governance | core | implemented | ratio | account, day | TABLES, TAG_REFERENCES, CLIENT_INPUTS |
| KPI-GOV-003 | Masking coverage on classified columns | governance | extended | implemented | ratio | account, day | TAG_REFERENCES, POLICY_REFERENCES |
| KPI-GOV-004 | DMF coverage on Tier-1 tables | governance | extended | implemented | ratio | account, day | TAG_REFERENCES, DATA_METRIC_FUNCTION_REFERENCES |
| KPI-GOV-005 | Data quality expectation violations | governance | core | implemented | violations | account, day | DATA_QUALITY_MONITORING_RESULTS |
| KPI-GOV-006 | Tier-1 column comment coverage | governance | extended | implemented | ratio | account, day | COLUMNS, TAG_REFERENCES |
| KPI-GOV-007 | Table comment coverage | governance | extended | implemented | ratio | account, day | TABLES |
| KPI-GOV-008 | DMF pass rate | governance | extended | implemented | ratio | account, day | DATA_QUALITY_MONITORING_RESULTS |
| KPI-GOV-009 | Data product health score | governance | advanced | planned | score | account, data_product, day | TAG_REFERENCES, DATA_QUALITY_MONITORING_RESULTS, TASK_HISTORY |
| KPI-GOV-010 | Classified columns | governance | extended | implemented | columns | account, day | TAG_REFERENCES |
| KPI-PERF-001 | Query time p50 / p95 by warehouse | performance | core | implemented | ms | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-002 | Queued time by warehouse | performance | core | implemented | seconds | account, warehouse, day | QUERY_HISTORY, WAREHOUSE_LOAD_HISTORY |
| KPI-PERF-003 | Spill to storage | performance | extended | implemented | gb | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-004 | Pruning efficiency | performance | extended | implemented | ratio | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-005 | Cache hit rate | performance | extended | implemented | ratio | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-006 | Compilation time p95 | performance | extended | implemented | ms | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-007 | Execution time per query signature | performance | advanced | implemented | ms | account, query_signature, day | QUERY_HISTORY |
| KPI-PERF-008 | Warehouse load (average running) | performance | extended | implemented | queries | account, warehouse, day | WAREHOUSE_LOAD_HISTORY |
| KPI-PERF-009 | Failed query rate | performance | extended | implemented | ratio | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-010 | Query acceleration eligible time | performance | extended | planned | seconds | account, warehouse, day | QUERY_HISTORY |
| KPI-PERF-011 | Long-running queries | performance | extended | implemented | queries | account, warehouse, day | QUERY_HISTORY |
| KPI-PHI-001 | Platform Health Index | health | extended | implemented | score | account, month | WAREHOUSE_METERING_HISTORY, QUERY_HISTORY, TASK_HISTORY, USERS, TAG_REFERENCES |
| KPI-PHI-002 | Health Index by WAF pillar | health | extended | implemented | score | account, waf_pillar, month | WAREHOUSE_METERING_HISTORY, QUERY_HISTORY, TASK_HISTORY, USERS, TAG_REFERENCES |
| KPI-PHI-003 | Peer benchmark position | health | advanced | planned | quartile | account, month |  |
| KPI-REL-001 | Task success rate | reliability | core | implemented | ratio | account, day | TASK_HISTORY |
| KPI-REL-002 | Failed tasks (24h) | reliability | core | implemented | runs | account, day | TASK_HISTORY, TASKS, TAG_REFERENCES |
| KPI-REL-003 | Freshness SLA attainment | reliability | extended | implemented | ratio | account, table, day | TASK_HISTORY, CLIENT_INPUTS |
| KPI-REL-004 | Harvest success rate | reliability | core | implemented | ratio | account, day | HARVEST_LOG |
| KPI-REL-005 | File load error rate | reliability | extended | implemented | ratio | account, table, day | COPY_HISTORY |
| KPI-REL-006 | Pipe latency | reliability | extended | planned | minutes | account, pipe, day | COPY_HISTORY |
| KPI-REL-007 | Dynamic table refresh lag | reliability | extended | planned | minutes | account, dynamic_table, day |  |
| KPI-REL-008 | Mean time to recover (tasks) | reliability | advanced | planned | hours | account, month | TASK_HISTORY |
| KPI-REL-009 | Downstream blast radius | reliability | advanced | planned | objects | account, task, day | TASK_HISTORY, TASKS, OBJECT_DEPENDENCIES, BI_REPORTS |
| KPI-REL-010 | Task retries | reliability | extended | implemented | runs | account, day | TASK_HISTORY |
| KPI-REL-011 | Replication / failover groups | reliability | extended | implemented | groups | account, day | REPLICATION_GROUPS |
| KPI-SEC-001 | MFA coverage | security | core | implemented | ratio | account, day | USERS |
| KPI-SEC-002 | ACCOUNTADMIN grantees | security | core | implemented | users | account, day | GRANTS_TO_USERS |
| KPI-SEC-003 | Failed logins | security | core | implemented | logins | account, day | LOGIN_HISTORY |
| KPI-SEC-004 | Dormant users | security | extended | implemented | users | account, day | USERS |
| KPI-SEC-005 | Network-policy coverage | security | extended | implemented | ratio | account, day | ACCOUNT_INFO, USERS |
| KPI-SEC-006 | Human users without MFA | security | core | implemented | users | account, day | USERS |
| KPI-SEC-007 | ACCOUNTADMIN activity | security | extended | implemented | queries | account, day | QUERY_HISTORY |
| KPI-SEC-008 | Service users with passwords | security | extended | implemented | users | account, day | USERS |
| KPI-SEC-009 | Direct object grants to users | security | extended | planned | grants | account, day | GRANTS_TO_USERS |
| KPI-SEC-010 | Orphan roles | security | extended | implemented | roles | account, day | ROLES, GRANTS_TO_USERS, GRANTS_TO_ROLES |
| KPI-SEC-011 | Anomalous access patterns | security | advanced | planned | events | account, user, day | LOGIN_HISTORY, ACCESS_HISTORY |
| KPI-SEC-012 | Failed login share | security | extended | implemented | ratio | account, day | LOGIN_HISTORY |
| KPI-USE-001 | Active users | usage | core | implemented | users | account, day | QUERY_HISTORY, USERS |
| KPI-USE-002 | Queries by client tool | usage | core | implemented | queries | account, client_tool, day | QUERY_HISTORY |
| KPI-USE-003 | Unused objects | usage | extended | implemented | tables | account, day | TABLES, ACCESS_HISTORY |
| KPI-USE-004 | Query volume by warehouse | usage | core | implemented | queries | account, warehouse, day | QUERY_HISTORY |
| KPI-USE-005 | Top consumers | usage | extended | implemented | credits | account, user, day | QUERY_ATTRIBUTION_HISTORY |
| KPI-USE-006 | Adoption by domain | usage | advanced | implemented | users | account, domain, day | ACCESS_HISTORY |
| KPI-USE-007 | BI report views (90 days) | usage | extended | implemented | views | account, report, day | BI_REPORTS |
| KPI-USE-008 | Cost per BI view | usage | advanced | planned | usd | account, report, day | BI_REPORTS, QUERY_ATTRIBUTION_HISTORY |
