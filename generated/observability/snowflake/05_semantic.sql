-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/observability/kpis. Regenerate with `altitude generate`.
USE DATABASE OBS;

CREATE OR REPLACE TABLE OBS.SEMANTIC.KPI_DEFINITIONS (
  KPI_ID VARCHAR, NAME VARCHAR, DOMAIN VARCHAR, TIER VARCHAR, STATUS VARCHAR, CERTIFIED BOOLEAN,
  DEFINITION VARCHAR, UNIT VARCHAR, GRAIN VARCHAR, AGGREGATION VARCHAR, DIRECTION VARCHAR, WAF_PILLAR VARCHAR,
  OWNER_ROLE VARCHAR, KPI_TABLE VARCHAR, SYNONYMS VARCHAR
) COMMENT = 'Certified KPI definitions (knowledge/observability/kpis)';

INSERT INTO OBS.SEMANTIC.KPI_DEFINITIONS VALUES
  ('KPI-AI-001', 'Cortex credits by function and agent', 'ai', 'core', 'implemented', TRUE, 'Cortex token credits per day by function and agent (DIMENSION = function / agent; ''(no agent)'' when direct).', 'credits', '["account", "function", "agent", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'AI_LEAD', 'OBS.KPI.KPI_AI_001', '["cortex", "cortex credits", "ai spend", "llm cost", "ai credits", "agent credits", "tokens cost"]'),
  ('KPI-AI-002', 'Cost per accepted answer', 'ai', 'extended', 'planned', FALSE, 'Cortex Agent cost / answers accepted by users (needs agent feedback events; not in the harvest contract yet).', 'usd', '["account", "agent", "day"]', 'avg', 'lower_is_better', 'cost_optimization', 'AI_LEAD', 'OBS.KPI.KPI_AI_002', '[]'),
  ('KPI-AI-003', 'Cortex tokens by model', 'ai', 'extended', 'implemented', TRUE, 'Tokens processed per model and day.', 'tokens', '["account", "model", "day"]', 'sum', 'neutral', 'cost_optimization', 'AI_LEAD', 'OBS.KPI.KPI_AI_003', '["tokens", "model usage", "llm tokens", "tokens by model"]'),
  ('KPI-AI-004', 'Cortex spend without agent identity', 'ai', 'extended', 'implemented', TRUE, 'Share of Cortex credits not attributable to a governed agent (direct calls by personal users), per day.', 'ratio', '["account", "day"]', 'avg', 'lower_is_better', 'security_governance', 'AI_LEAD', 'OBS.KPI.KPI_AI_004', '["ungoverned ai", "cortex without agent", "direct cortex usage", "unbudgeted ai"]'),
  ('KPI-AI-005', 'Cortex call latency', 'ai', 'extended', 'implemented', TRUE, 'Average seconds per Cortex call, per function and day.', 'seconds', '["account", "function", "day"]', 'avg', 'lower_is_better', 'performance_efficiency', 'AI_LEAD', 'OBS.KPI.KPI_AI_005', '["cortex latency", "ai latency", "llm latency", "agent latency"]'),
  ('KPI-AI-006', 'Semantic views', 'ai', 'extended', 'implemented', TRUE, 'Number of semantic views in the account, per snapshot day (AI readiness of top KPI domains).', 'views', '["account", "day"]', 'latest', 'higher_is_better', 'operational_excellence', 'AI_LEAD', 'OBS.KPI.KPI_AI_006', '["semantic views", "semantic layer", "certified kpis"]'),
  ('KPI-AI-007', 'Agent evaluation drift', 'ai', 'advanced', 'planned', FALSE, 'Change in golden-question pass rate of in-account agents between evaluation runs.', 'ratio', '["account", "agent", "day"]', 'latest', 'higher_is_better', 'operational_excellence', 'AI_LEAD', 'OBS.KPI.KPI_AI_007', '[]'),
  ('KPI-AI-008', 'Agent warehouse credits', 'ai', 'extended', 'planned', FALSE, 'Warehouse credits consumed by agent roles (needs role on attribution rows).', 'credits', '["account", "agent", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'AI_LEAD', 'OBS.KPI.KPI_AI_008', '[]'),
  ('KPI-COST-001', 'Credits by account, warehouse and day', 'cost', 'core', 'implemented', TRUE, 'Credits billed per warehouse and day: compute + cloud services credits from WAREHOUSE_METERING_HISTORY, with the account-day cloud-services adjustment from METERING_DAILY_HISTORY allocated pro rata to cloud-services use.', 'credits', '["account", "warehouse", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_001', '["credits", "credit usage", "warehouse credits", "compute credits", "consumption", "burn"]'),
  ('KPI-COST-002', 'Spend ($) by warehouse and day', 'cost', 'core', 'implemented', TRUE, 'KPI-COST-001 credits billed multiplied by the contract price per credit (client input).', 'usd', '["account", "warehouse", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_002', '["spend", "cost", "dollars", "money", "warehouse cost", "how much did we spend"]'),
  ('KPI-COST-003', 'Cost by cost centre', 'cost', 'core', 'implemented', TRUE, 'Daily billed cost ($) by cost centre: warehouse spend by the warehouse''s cost-centre tag; serverless, AI and untagged warehouse spend fall into UNALLOCATED. Sums to total billed spend (KPI-COST-011).', 'usd', '["account", "cost_centre", "day"]', 'sum', 'neutral', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_003', '["cost centre", "cost center", "chargeback", "showback", "department", "business unit", "tag"]'),
  ('KPI-COST-004', 'Month-on-month spend trend', 'cost', 'core', 'implemented', TRUE, 'Percent change in average daily billed spend versus the previous calendar month (average daily spend makes partial months comparable).', 'percent', '["account", "month"]', 'latest', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_004', '["month on month", "mom", "trend", "growth", "compared to last month", "monthly trend"]'),
  ('KPI-COST-005', 'Forecast vs budget', 'cost', 'core', 'implemented', TRUE, 'Month-end forecast of billed credits (month-to-date run rate x days in month) divided by the account budget''s monthly spending limit (credits). Above 1.0 the month is forecast to overrun.', 'ratio', '["account", "month"]', 'latest', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_005', '["forecast", "budget", "overrun", "on track", "projection", "run rate"]'),
  ('KPI-COST-006', 'Cost per query signature', 'cost', 'extended', 'implemented', TRUE, 'Compute credits attributed to each parameterised query signature per day, in dollars.', 'usd', '["account", "query_signature", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_006', '["query signature", "expensive queries", "query cost", "top queries", "costliest queries"]'),
  ('KPI-COST-007', 'Idle credit share', 'cost', 'extended', 'implemented', TRUE, 'compute credits billed while the warehouse had no running queries / total compute credits', 'ratio', '["account", "warehouse", "day"]', 'avg', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_007', '["idle", "idle credits", "idle share", "wasted credits", "auto suspend", "unused compute"]'),
  ('KPI-COST-008', 'Serverless credit breakdown', 'cost', 'extended', 'implemented', TRUE, 'Credits per day by serverless service type (clustering, search optimisation, MV refresh, Snowpipe, AI services).', 'credits', '["account", "service_type", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_008', '["serverless", "clustering credits", "snowpipe", "automatic clustering", "search optimization", "materialized view"]'),
  ('KPI-COST-009', 'Storage by type', 'cost', 'extended', 'implemented', TRUE, 'Average stored terabytes per day by storage type (database, stage, fail-safe, hybrid).', 'tb', '["account", "storage_type", "day"]', 'avg', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_009', '["storage", "terabytes", "tb", "failsafe", "stage storage", "storage by type"]'),
  ('KPI-COST-010', 'Credits billed by service type and day', 'cost', 'core', 'implemented', TRUE, 'Billing truth — METERING_DAILY_HISTORY credits billed per service type and day.', 'credits', '["account", "service_type", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_010', '["billed credits", "billing", "invoice", "service type", "metering"]'),
  ('KPI-COST-011', 'Total spend ($) by account and day', 'cost', 'core', 'implemented', TRUE, 'All billed credits (every service type) for the account-day multiplied by the contract price.', 'usd', '["account", "day"]', 'sum', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_011', '["total spend", "total cost", "account spend", "overall cost", "bill"]'),
  ('KPI-COST-012', 'Storage cost per month', 'cost', 'extended', 'implemented', TRUE, 'Average stored TB (database + stage + fail-safe + hybrid) in the month x contract storage price per TB-month.', 'usd', '["account", "month"]', 'latest', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_012', '["storage cost", "storage spend", "storage bill"]'),
  ('KPI-COST-013', 'Capacity commitment burn-down', 'cost', 'advanced', 'implemented', TRUE, 'Cumulative billed credits since the commitment start / annual committed credits, per day; compare with EXPECTED_SHARE (elapsed share of the commitment term).', 'ratio', '["account", "day"]', 'latest', 'neutral', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_013', '["commitment", "capacity", "burn down", "contract", "prepaid credits"]'),
  ('KPI-COST-015', 'Cloud services ratio', 'cost', 'extended', 'implemented', TRUE, 'Cloud-services credits used / compute credits used for warehouse metering, per account and day.', 'ratio', '["account", "day"]', 'avg', 'lower_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_015', '["cloud services", "cloud services ratio", "metadata cost"]'),
  ('KPI-COST-016', 'Unit cost per dashboard view', 'cost', 'advanced', 'planned', FALSE, 'BI refresh and query cost attributed to a dashboard / its views in the period.', 'usd', '["account", "report", "month"]', 'latest', 'lower_is_better', 'cost_optimization', 'BI_LEAD', 'OBS.KPI.KPI_COST_016', '[]'),
  ('KPI-COST-017', 'Unit cost per data product', 'cost', 'advanced', 'planned', FALSE, 'Compute, storage and serverless cost attributed to each data product (by data-product tag).', 'usd', '["account", "data_product", "month"]', 'latest', 'lower_is_better', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_017', '[]'),
  ('KPI-COST-018', 'Cost per agent answer', 'cost', 'advanced', 'planned', FALSE, 'Cortex Agent token cost plus agent warehouse cost per answered question.', 'usd', '["account", "agent", "day"]', 'avg', 'lower_is_better', 'cost_optimization', 'AI_LEAD', 'OBS.KPI.KPI_COST_018', '[]'),
  ('KPI-COST-019', 'Credits by role', 'cost', 'extended', 'planned', FALSE, 'Attributed compute credits by executing role per day (needs ROLE_NAME on attribution rows).', 'credits', '["account", "role", "day"]', 'sum', 'neutral', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_COST_019', '[]'),
  ('KPI-COST-020', 'Resource monitor coverage', 'cost', 'extended', 'implemented', TRUE, 'Share of warehouses with a resource monitor attached, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'cost_optimization', 'PLATFORM_OWNER', 'OBS.KPI.KPI_COST_020', '["resource monitor", "monitor coverage", "quota"]'),
  ('KPI-GOV-001', 'Tag coverage', 'governance', 'core', 'implemented', TRUE, 'Share of tables carrying at least one object-level tag, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_001', '["tag coverage", "tagged tables", "tagging", "classification coverage"]'),
  ('KPI-GOV-002', 'Owner coverage on Tier-1 objects', 'governance', 'core', 'implemented', TRUE, 'Share of Tier-1 tables (TIER tag = tier1) carrying the owner tag, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_002', '["owner coverage", "ownership", "data owner", "tier 1 owners", "stewardship"]'),
  ('KPI-GOV-003', 'Masking coverage on classified columns', 'governance', 'extended', 'implemented', TRUE, 'Share of PII-tagged columns with an active masking policy, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_003', '["masking", "masking coverage", "pii", "sensitive columns", "data protection"]'),
  ('KPI-GOV-004', 'DMF coverage on Tier-1 tables', 'governance', 'extended', 'implemented', TRUE, 'Share of Tier-1 tables with at least one data metric function attached, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_004', '["dmf", "data metric functions", "data quality coverage", "dq coverage", "quality monitoring"]'),
  ('KPI-GOV-005', 'Data quality expectation violations', 'governance', 'core', 'implemented', TRUE, 'Number of data metric function results that violated their expectation, per account and day.', 'violations', '["account", "day"]', 'sum', 'lower_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_005', '["data quality", "dq violations", "quality issues", "expectation violations"]'),
  ('KPI-GOV-006', 'Tier-1 column comment coverage', 'governance', 'extended', 'implemented', TRUE, 'Share of columns on Tier-1 tables with a comment, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_006', '["comments", "column comments", "documentation", "described columns"]'),
  ('KPI-GOV-007', 'Table comment coverage', 'governance', 'extended', 'implemented', TRUE, 'Share of tables with a table-level comment, per snapshot day.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_007', '["table comments", "described tables"]'),
  ('KPI-GOV-008', 'DMF pass rate', 'governance', 'extended', 'implemented', TRUE, 'Share of data metric function results that met their expectation, per account and day.', 'ratio', '["account", "day"]', 'avg', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_008', '["dmf pass rate", "quality pass rate", "data quality score"]'),
  ('KPI-GOV-009', 'Data product health score', 'governance', 'advanced', 'planned', FALSE, 'Composite of freshness, quality, ownership and documentation per data product.', 'score', '["account", "data_product", "day"]', 'latest', 'higher_is_better', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_009', '[]'),
  ('KPI-GOV-010', 'Classified columns', 'governance', 'extended', 'implemented', TRUE, 'Number of columns carrying a PII classification tag, per snapshot day.', 'columns', '["account", "day"]', 'latest', 'neutral', 'security_governance', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_GOV_010', '["classified columns", "pii columns", "sensitive data inventory"]'),
  ('KPI-PHI-001', 'Platform Health Index', 'health', 'extended', 'implemented', TRUE, '0-100 index: rubric-weighted mean of WAF pillar scores, each the mean attainment of that pillar''s targeted KPIs (KPI monthly value vs its rubric target, capped at 1).', 'score', '["account", "month"]', 'latest', 'higher_is_better', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PHI_001', '["health index", "platform health", "health score", "overall health", "scorecard"]'),
  ('KPI-PHI-002', 'Health Index by WAF pillar', 'health', 'extended', 'implemented', TRUE, 'Pillar scores (0-100) behind KPI-PHI-001, one per Well-Architected pillar and month.', 'score', '["account", "waf_pillar", "month"]', 'latest', 'higher_is_better', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PHI_002', '["pillar score", "waf pillar", "well architected", "pillar health"]'),
  ('KPI-PHI-003', 'Peer benchmark position', 'health', 'advanced', 'planned', FALSE, 'Quartile of the Health Index among anonymised peers by industry and spend band (opt-in benchmarking).', 'quartile', '["account", "month"]', 'latest', 'higher_is_better', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PHI_003', '[]'),
  ('KPI-PERF-001', 'Query time p50 / p95 by warehouse', 'performance', 'core', 'implemented', TRUE, 'Median and 95th-percentile total elapsed time (ms) of successful queries per warehouse and day; VALUE is p95.', 'ms', '["account", "warehouse", "day"]', 'avg', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_001', '["query time", "latency", "p95", "p50", "median query time", "slow queries", "response time", "elapsed time"]'),
  ('KPI-PERF-002', 'Queued time by warehouse', 'performance', 'core', 'implemented', TRUE, 'Total seconds queries spent queued for warehouse overload per warehouse and day.', 'seconds', '["account", "warehouse", "day"]', 'sum', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_002', '["queued", "queueing", "queue time", "waiting", "concurrency", "overload"]'),
  ('KPI-PERF-003', 'Spill to storage', 'performance', 'extended', 'implemented', TRUE, 'Gigabytes spilled to local plus remote storage per warehouse and day.', 'gb', '["account", "warehouse", "day"]', 'sum', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_003', '["spill", "spilling", "spilled bytes", "remote spill", "local spill", "memory"]'),
  ('KPI-PERF-004', 'Pruning efficiency', 'performance', 'extended', 'implemented', TRUE, '1 - partitions scanned / partitions total, over queries that touched partitioned tables, per warehouse and day.', 'ratio', '["account", "warehouse", "day"]', 'avg', 'higher_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_004', '["pruning", "partition pruning", "micro partitions", "scanned partitions", "clustering effectiveness"]'),
  ('KPI-PERF-005', 'Cache hit rate', 'performance', 'extended', 'implemented', TRUE, 'Average share of scanned data served from the warehouse cache (PERCENTAGE_SCANNED_FROM_CACHE) per warehouse and day.', 'ratio', '["account", "warehouse", "day"]', 'avg', 'higher_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_005', '["cache", "cache hit", "result cache", "warehouse cache", "cache rate"]'),
  ('KPI-PERF-006', 'Compilation time p95', 'performance', 'extended', 'implemented', TRUE, '95th-percentile compilation time (ms) per warehouse and day.', 'ms', '["account", "warehouse", "day"]', 'avg', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_006', '["compilation", "compile time", "planning time"]'),
  ('KPI-PERF-007', 'Execution time per query signature', 'performance', 'advanced', 'implemented', TRUE, 'Average execution time (ms) per parameterised query signature and day — the series the regression alert compares against its forecast band.', 'ms', '["account", "query_signature", "day"]', 'avg', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_007', '["regression", "signature performance", "query regression", "slower than usual"]'),
  ('KPI-PERF-008', 'Warehouse load (average running)', 'performance', 'extended', 'implemented', TRUE, 'Average number of running queries per active hour, per warehouse and day (WAREHOUSE_LOAD_HISTORY).', 'queries', '["account", "warehouse", "day"]', 'avg', 'neutral', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_008', '["load", "concurrency", "utilisation", "utilization", "running queries"]'),
  ('KPI-PERF-009', 'Failed query rate', 'performance', 'extended', 'implemented', TRUE, 'Share of queries that did not succeed, per warehouse and day.', 'ratio', '["account", "warehouse", "day"]', 'avg', 'lower_is_better', 'reliability', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_009', '["failed queries", "query errors", "error rate"]'),
  ('KPI-PERF-010', 'Query acceleration eligible time', 'performance', 'extended', 'planned', FALSE, 'Seconds of eligible query acceleration per warehouse (QUERY_ACCELERATION_ELIGIBLE; not in the harvest contract yet).', 'seconds', '["account", "warehouse", "day"]', 'sum', 'neutral', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_010', '[]'),
  ('KPI-PERF-011', 'Long-running queries', 'performance', 'extended', 'implemented', TRUE, 'Number of queries whose elapsed time exceeds the rubric long-query limit, per warehouse and day.', 'queries', '["account", "warehouse", "day"]', 'sum', 'lower_is_better', 'performance_efficiency', 'PLATFORM_OWNER', 'OBS.KPI.KPI_PERF_011', '["long running", "long queries", "runaway queries"]'),
  ('KPI-REL-001', 'Task success rate', 'reliability', 'core', 'implemented', TRUE, 'Succeeded task runs / all task runs (failed and skipped runs count as unsuccessful) per account and day.', 'ratio', '["account", "day"]', 'avg', 'higher_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_001', '["task success", "task success rate", "pipeline success", "job success", "task reliability"]'),
  ('KPI-REL-002', 'Failed tasks (24h)', 'reliability', 'core', 'implemented', TRUE, 'Number of failed task runs per account and day; FAILED_TIER1 counts tasks loading Tier-1 tables.', 'runs', '["account", "day"]', 'sum', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_002', '["failed tasks", "task failures", "broken pipelines", "failed jobs", "failures"]'),
  ('KPI-REL-003', 'Freshness SLA attainment', 'reliability', 'extended', 'implemented', TRUE, '1 when the table''s loading task succeeded before the client''s daily deadline, else 0; averaged over a window it is the attainment rate.', 'ratio', '["account", "table", "day"]', 'avg', 'higher_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_003', '["freshness", "sla", "late data", "freshness sla", "on time", "data late"]'),
  ('KPI-REL-004', 'Harvest success rate', 'reliability', 'core', 'implemented', TRUE, 'Successful (or intentionally skipped) harvest steps / all harvest steps per account and day (Section 7.8 target ≥ 99%).', 'ratio', '["account", "day"]', 'avg', 'higher_is_better', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_REL_004', '["harvest", "harvest success", "observability pipeline", "telemetry collection"]'),
  ('KPI-REL-005', 'File load error rate', 'reliability', 'extended', 'implemented', TRUE, 'Share of files loaded by COPY / Snowpipe with a status other than Loaded, per target table and day.', 'ratio', '["account", "table", "day"]', 'avg', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_005', '["copy errors", "load errors", "snowpipe errors", "file load failures"]'),
  ('KPI-REL-006', 'Pipe latency', 'reliability', 'extended', 'planned', FALSE, 'Minutes between file arrival and load for each pipe (needs PIPE ingestion timestamps; not in the harvest contract yet).', 'minutes', '["account", "pipe", "day"]', 'avg', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_006', '[]'),
  ('KPI-REL-007', 'Dynamic table refresh lag', 'reliability', 'extended', 'planned', FALSE, 'Actual vs target lag per dynamic table (DYNAMIC_TABLE_REFRESH_HISTORY; not in the harvest contract yet).', 'minutes', '["account", "dynamic_table", "day"]', 'max', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_007', '[]'),
  ('KPI-REL-008', 'Mean time to recover (tasks)', 'reliability', 'advanced', 'planned', FALSE, 'Hours from a task''s first failure to its next successful run, averaged per month.', 'hours', '["account", "month"]', 'avg', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_008', '[]'),
  ('KPI-REL-009', 'Downstream blast radius', 'reliability', 'advanced', 'planned', FALSE, 'Number of downstream tasks, tables and dashboards affected by a failed task (task graph + object dependencies).', 'objects', '["account", "task", "day"]', 'max', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_009', '[]'),
  ('KPI-REL-010', 'Task retries', 'reliability', 'extended', 'implemented', TRUE, 'Number of task runs that needed more than one attempt, per account and day.', 'runs', '["account", "day"]', 'sum', 'lower_is_better', 'reliability', 'DATAOPS_LEAD', 'OBS.KPI.KPI_REL_010', '["retries", "retried tasks", "flaky tasks"]'),
  ('KPI-REL-011', 'Replication / failover groups', 'reliability', 'extended', 'implemented', TRUE, 'Number of replication or failover groups configured, per snapshot day.', 'groups', '["account", "day"]', 'latest', 'higher_is_better', 'reliability', 'PLATFORM_OWNER', 'OBS.KPI.KPI_REL_011', '["replication", "failover", "disaster recovery", "dr"]'),
  ('KPI-SEC-001', 'MFA coverage', 'security', 'core', 'implemented', TRUE, 'Share of enabled human users protected by MFA: HAS_MFA, or SSO-only users without a password (MFA enforced by the identity provider).', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_001', '["mfa", "multi factor", "2fa", "mfa coverage", "two factor"]'),
  ('KPI-SEC-002', 'ACCOUNTADMIN grantees', 'security', 'core', 'implemented', TRUE, 'Number of users granted the ACCOUNTADMIN role, per snapshot day.', 'users', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_002', '["accountadmin", "account admin", "admins", "privileged users", "administrators"]'),
  ('KPI-SEC-003', 'Failed logins', 'security', 'core', 'implemented', TRUE, 'Number of failed login attempts per account and day.', 'logins', '["account", "day"]', 'sum', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_003', '["failed logins", "login failures", "brute force", "authentication failures"]'),
  ('KPI-SEC-004', 'Dormant users', 'security', 'extended', 'implemented', TRUE, 'Enabled human users with no successful login within the rubric dormancy window, per snapshot day.', 'users', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_004', '["dormant", "inactive users", "stale users", "unused accounts"]'),
  ('KPI-SEC-005', 'Network-policy coverage', 'security', 'extended', 'implemented', TRUE, '1.0 when an account-level network policy is set; otherwise the share of users with a user-level network policy.', 'ratio', '["account", "day"]', 'latest', 'higher_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_005', '["network policy", "ip allow list", "network rules", "network coverage"]'),
  ('KPI-SEC-006', 'Human users without MFA', 'security', 'core', 'implemented', TRUE, 'Number of enabled human users not protected by MFA (complement of KPI-SEC-001), per snapshot day.', 'users', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_006', '["without mfa", "no mfa", "users missing mfa", "unprotected users"]'),
  ('KPI-SEC-007', 'ACCOUNTADMIN activity', 'security', 'extended', 'implemented', TRUE, 'Queries executed under the ACCOUNTADMIN role per account and day (USERS = distinct users).', 'queries', '["account", "day"]', 'sum', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_007', '["accountadmin use", "admin activity", "privileged activity", "break glass"]'),
  ('KPI-SEC-008', 'Service users with passwords', 'security', 'extended', 'implemented', TRUE, 'Service (or legacy service) users that still authenticate with a password, per snapshot day.', 'users', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_008', '["service users", "service accounts", "password service users", "legacy service"]'),
  ('KPI-SEC-009', 'Direct object grants to users', 'security', 'extended', 'planned', FALSE, 'Object privileges granted directly to users rather than via roles (needs GRANTS_TO_USERS privilege rows).', 'grants', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_009', '[]'),
  ('KPI-SEC-010', 'Orphan roles', 'security', 'extended', 'implemented', TRUE, 'Non-system roles granted to no user and no role (current snapshot).', 'roles', '["account", "day"]', 'latest', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_010', '["orphan roles", "unused roles", "role cleanup"]'),
  ('KPI-SEC-011', 'Anomalous access patterns', 'security', 'advanced', 'planned', FALSE, 'Logins or object access outside a user''s learned baseline (time, IP range, objects).', 'events', '["account", "user", "day"]', 'sum', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_011', '[]'),
  ('KPI-SEC-012', 'Failed login share', 'security', 'extended', 'implemented', TRUE, 'Failed login attempts / all login attempts per account and day.', 'ratio', '["account", "day"]', 'avg', 'lower_is_better', 'security_governance', 'SECURITY_LEAD', 'OBS.KPI.KPI_SEC_012', '["login failure rate", "failed login share"]'),
  ('KPI-USE-001', 'Active users', 'usage', 'core', 'implemented', TRUE, 'Distinct users who ran at least one query, per account and day (HUMAN_USERS excludes service users).', 'users', '["account", "day"]', 'avg', 'higher_is_better', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_USE_001', '["active users", "users", "daily active users", "dau", "adoption", "how many users"]'),
  ('KPI-USE-002', 'Queries by client tool', 'usage', 'core', 'implemented', TRUE, 'Number of queries per client application (driver / tool) and day.', 'queries', '["account", "client_tool", "day"]', 'sum', 'neutral', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_USE_002', '["client tool", "tools", "applications", "power bi", "dbt", "drivers", "which tools"]'),
  ('KPI-USE-003', 'Unused objects', 'usage', 'extended', 'implemented', TRUE, 'Tables with no recorded access within the rubric window before the snapshot day.', 'tables', '["account", "day"]', 'latest', 'lower_is_better', 'cost_optimization', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_USE_003', '["unused", "unused tables", "stale objects", "unaccessed tables", "dead tables"]'),
  ('KPI-USE-004', 'Query volume by warehouse', 'usage', 'core', 'implemented', TRUE, 'Number of queries per warehouse and day.', 'queries', '["account", "warehouse", "day"]', 'sum', 'neutral', 'operational_excellence', 'PLATFORM_OWNER', 'OBS.KPI.KPI_USE_004', '["query volume", "number of queries", "query count", "how many queries", "workload"]'),
  ('KPI-USE-005', 'Top consumers', 'usage', 'extended', 'implemented', TRUE, 'Compute credits attributed to each user per day (top consumers).', 'credits', '["account", "user", "day"]', 'sum', 'neutral', 'cost_optimization', 'FINOPS_LEAD', 'OBS.KPI.KPI_USE_005', '["top consumers", "top users", "heaviest users", "who uses the most", "biggest spenders"]'),
  ('KPI-USE-006', 'Adoption by domain', 'usage', 'advanced', 'implemented', TRUE, 'Distinct users reading objects in each database schema (data domain) per day.', 'users', '["account", "domain", "day"]', 'avg', 'higher_is_better', 'operational_excellence', 'DATA_GOVERNANCE_LEAD', 'OBS.KPI.KPI_USE_006', '["adoption by domain", "domain adoption", "schema usage"]'),
  ('KPI-USE-007', 'BI report views (90 days)', 'usage', 'extended', 'implemented', TRUE, 'Views in the last 90 days per BI report, per snapshot day (BI metadata).', 'views', '["account", "report", "day"]', 'latest', 'neutral', 'operational_excellence', 'BI_LEAD', 'OBS.KPI.KPI_USE_007', '["report views", "dashboard views", "bi usage", "report usage"]'),
  ('KPI-USE-008', 'Cost per BI view', 'usage', 'advanced', 'planned', FALSE, 'Query and refresh cost of a report''s signature over 90 days / its views over 90 days.', 'usd', '["account", "report", "day"]', 'latest', 'lower_is_better', 'cost_optimization', 'BI_LEAD', 'OBS.KPI.KPI_USE_008', '[]');

CREATE OR REPLACE VIEW OBS.SEMANTIC.KPI_VALUES AS
SELECT 'KPI-AI-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_AI_001
UNION ALL
SELECT 'KPI-AI-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_AI_003
UNION ALL
SELECT 'KPI-AI-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_AI_004
UNION ALL
SELECT 'KPI-AI-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_AI_005
UNION ALL
SELECT 'KPI-AI-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_AI_006
UNION ALL
SELECT 'KPI-COST-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_001
UNION ALL
SELECT 'KPI-COST-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_002
UNION ALL
SELECT 'KPI-COST-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_003
UNION ALL
SELECT 'KPI-COST-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_004
UNION ALL
SELECT 'KPI-COST-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_005
UNION ALL
SELECT 'KPI-COST-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_006
UNION ALL
SELECT 'KPI-COST-007' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_007
UNION ALL
SELECT 'KPI-COST-008' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_008
UNION ALL
SELECT 'KPI-COST-009' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_009
UNION ALL
SELECT 'KPI-COST-010' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_010
UNION ALL
SELECT 'KPI-COST-011' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_011
UNION ALL
SELECT 'KPI-COST-012' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_012
UNION ALL
SELECT 'KPI-COST-013' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_013
UNION ALL
SELECT 'KPI-COST-015' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_015
UNION ALL
SELECT 'KPI-COST-020' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_COST_020
UNION ALL
SELECT 'KPI-GOV-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_001
UNION ALL
SELECT 'KPI-GOV-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_002
UNION ALL
SELECT 'KPI-GOV-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_003
UNION ALL
SELECT 'KPI-GOV-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_004
UNION ALL
SELECT 'KPI-GOV-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_005
UNION ALL
SELECT 'KPI-GOV-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_006
UNION ALL
SELECT 'KPI-GOV-007' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_007
UNION ALL
SELECT 'KPI-GOV-008' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_008
UNION ALL
SELECT 'KPI-GOV-010' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_GOV_010
UNION ALL
SELECT 'KPI-PHI-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PHI_001
UNION ALL
SELECT 'KPI-PHI-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PHI_002
UNION ALL
SELECT 'KPI-PERF-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_001
UNION ALL
SELECT 'KPI-PERF-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_002
UNION ALL
SELECT 'KPI-PERF-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_003
UNION ALL
SELECT 'KPI-PERF-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_004
UNION ALL
SELECT 'KPI-PERF-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_005
UNION ALL
SELECT 'KPI-PERF-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_006
UNION ALL
SELECT 'KPI-PERF-007' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_007
UNION ALL
SELECT 'KPI-PERF-008' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_008
UNION ALL
SELECT 'KPI-PERF-009' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_009
UNION ALL
SELECT 'KPI-PERF-011' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_PERF_011
UNION ALL
SELECT 'KPI-REL-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_001
UNION ALL
SELECT 'KPI-REL-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_002
UNION ALL
SELECT 'KPI-REL-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_003
UNION ALL
SELECT 'KPI-REL-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_004
UNION ALL
SELECT 'KPI-REL-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_005
UNION ALL
SELECT 'KPI-REL-010' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_010
UNION ALL
SELECT 'KPI-REL-011' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_REL_011
UNION ALL
SELECT 'KPI-SEC-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_001
UNION ALL
SELECT 'KPI-SEC-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_002
UNION ALL
SELECT 'KPI-SEC-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_003
UNION ALL
SELECT 'KPI-SEC-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_004
UNION ALL
SELECT 'KPI-SEC-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_005
UNION ALL
SELECT 'KPI-SEC-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_006
UNION ALL
SELECT 'KPI-SEC-007' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_007
UNION ALL
SELECT 'KPI-SEC-008' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_008
UNION ALL
SELECT 'KPI-SEC-010' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_010
UNION ALL
SELECT 'KPI-SEC-012' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_SEC_012
UNION ALL
SELECT 'KPI-USE-001' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_001
UNION ALL
SELECT 'KPI-USE-002' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_002
UNION ALL
SELECT 'KPI-USE-003' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_003
UNION ALL
SELECT 'KPI-USE-004' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_004
UNION ALL
SELECT 'KPI-USE-005' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_005
UNION ALL
SELECT 'KPI-USE-006' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_006
UNION ALL
SELECT 'KPI-USE-007' AS KPI_ID, ACCOUNT_NAME, PERIOD, DIMENSION, VALUE FROM OBS.KPI.KPI_USE_007;

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_AI
  TABLES (
    kpi_ai_001 AS OBS.KPI.KPI_AI_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('cortex', 'cortex credits', 'ai spend', 'llm cost', 'ai credits', 'agent credits')
      COMMENT = 'Cortex credits by function and agent',
    kpi_ai_003 AS OBS.KPI.KPI_AI_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('tokens', 'model usage', 'llm tokens', 'tokens by model')
      COMMENT = 'Cortex tokens by model',
    kpi_ai_004 AS OBS.KPI.KPI_AI_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('ungoverned ai', 'cortex without agent', 'direct cortex usage', 'unbudgeted ai')
      COMMENT = 'Cortex spend without agent identity',
    kpi_ai_005 AS OBS.KPI.KPI_AI_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('cortex latency', 'ai latency', 'llm latency', 'agent latency')
      COMMENT = 'Cortex call latency',
    kpi_ai_006 AS OBS.KPI.KPI_AI_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('semantic views', 'semantic layer', 'certified kpis')
      COMMENT = 'Semantic views'
  )
  DIMENSIONS (
    kpi_ai_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_ai_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_ai_001.function_agent_kpi_ai_001 AS DIMENSION COMMENT = 'function_agent',
    kpi_ai_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_ai_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_ai_003.model_kpi_ai_003 AS DIMENSION COMMENT = 'model',
    kpi_ai_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_ai_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_ai_004.none_kpi_ai_004 AS DIMENSION COMMENT = 'none',
    kpi_ai_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_ai_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_ai_005.function_kpi_ai_005 AS DIMENSION COMMENT = 'function',
    kpi_ai_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_ai_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_ai_006.none_kpi_ai_006 AS DIMENSION COMMENT = 'none'
  )
  METRICS (
    kpi_ai_001.cortex_credits_by_function_and_agent AS SUM(VALUE)
      COMMENT = 'KPI-AI-001 [credits] Cortex token credits per day by function and agent (DIMENSION = function / agent; (no agent) when direct).',
    kpi_ai_003.cortex_tokens_by_model AS SUM(VALUE)
      COMMENT = 'KPI-AI-003 [tokens] Tokens processed per model and day.',
    kpi_ai_004.cortex_spend_without_agent_identity AS AVG(VALUE)
      COMMENT = 'KPI-AI-004 [ratio] Share of Cortex credits not attributable to a governed agent (direct calls by personal users), per day.',
    kpi_ai_005.cortex_call_latency AS AVG(VALUE)
      COMMENT = 'KPI-AI-005 [seconds] Average seconds per Cortex call, per function and day.',
    kpi_ai_006.semantic_views AS MAX(VALUE)
      COMMENT = 'KPI-AI-006 [views] Number of semantic views in the account, per snapshot day (AI readiness of top KPI domains).'
  )
  COMMENT = 'Certified ai KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_COST
  TABLES (
    kpi_cost_001 AS OBS.KPI.KPI_COST_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('credits', 'credit usage', 'warehouse credits', 'compute credits', 'consumption', 'burn')
      COMMENT = 'Credits by account, warehouse and day',
    kpi_cost_002 AS OBS.KPI.KPI_COST_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('spend', 'cost', 'dollars', 'money', 'warehouse cost', 'how much did we spend')
      COMMENT = 'Spend ($) by warehouse and day',
    kpi_cost_003 AS OBS.KPI.KPI_COST_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('cost centre', 'cost center', 'chargeback', 'showback', 'department', 'business unit')
      COMMENT = 'Cost by cost centre',
    kpi_cost_004 AS OBS.KPI.KPI_COST_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('month on month', 'mom', 'trend', 'growth', 'compared to last month', 'monthly trend')
      COMMENT = 'Month-on-month spend trend',
    kpi_cost_005 AS OBS.KPI.KPI_COST_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('forecast', 'budget', 'overrun', 'on track', 'projection', 'run rate')
      COMMENT = 'Forecast vs budget',
    kpi_cost_006 AS OBS.KPI.KPI_COST_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('query signature', 'expensive queries', 'query cost', 'top queries', 'costliest queries')
      COMMENT = 'Cost per query signature',
    kpi_cost_007 AS OBS.KPI.KPI_COST_007
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('idle', 'idle credits', 'idle share', 'wasted credits', 'auto suspend', 'unused compute')
      COMMENT = 'Idle credit share',
    kpi_cost_008 AS OBS.KPI.KPI_COST_008
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('serverless', 'clustering credits', 'snowpipe', 'automatic clustering', 'search optimization', 'materialized view')
      COMMENT = 'Serverless credit breakdown',
    kpi_cost_009 AS OBS.KPI.KPI_COST_009
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('storage', 'terabytes', 'tb', 'failsafe', 'stage storage', 'storage by type')
      COMMENT = 'Storage by type',
    kpi_cost_010 AS OBS.KPI.KPI_COST_010
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('billed credits', 'billing', 'invoice', 'service type', 'metering')
      COMMENT = 'Credits billed by service type and day',
    kpi_cost_011 AS OBS.KPI.KPI_COST_011
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('total spend', 'total cost', 'account spend', 'overall cost', 'bill')
      COMMENT = 'Total spend ($) by account and day',
    kpi_cost_012 AS OBS.KPI.KPI_COST_012
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('storage cost', 'storage spend', 'storage bill')
      COMMENT = 'Storage cost per month',
    kpi_cost_013 AS OBS.KPI.KPI_COST_013
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('commitment', 'capacity', 'burn down', 'contract', 'prepaid credits')
      COMMENT = 'Capacity commitment burn-down',
    kpi_cost_015 AS OBS.KPI.KPI_COST_015
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('cloud services', 'cloud services ratio', 'metadata cost')
      COMMENT = 'Cloud services ratio',
    kpi_cost_020 AS OBS.KPI.KPI_COST_020
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('resource monitor', 'monitor coverage', 'quota')
      COMMENT = 'Resource monitor coverage'
  )
  DIMENSIONS (
    kpi_cost_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_001.warehouse_kpi_cost_001 AS DIMENSION COMMENT = 'warehouse',
    kpi_cost_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_002.warehouse_kpi_cost_002 AS DIMENSION COMMENT = 'warehouse',
    kpi_cost_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_003.cost_centre_kpi_cost_003 AS DIMENSION COMMENT = 'cost_centre',
    kpi_cost_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_004.none_kpi_cost_004 AS DIMENSION COMMENT = 'none',
    kpi_cost_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_005.none_kpi_cost_005 AS DIMENSION COMMENT = 'none',
    kpi_cost_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_006.query_signature_kpi_cost_006 AS DIMENSION COMMENT = 'query_signature',
    kpi_cost_007.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_007.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_007.warehouse_kpi_cost_007 AS DIMENSION COMMENT = 'warehouse',
    kpi_cost_008.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_008.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_008.service_type_kpi_cost_008 AS DIMENSION COMMENT = 'service_type',
    kpi_cost_009.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_009.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_009.storage_type_kpi_cost_009 AS DIMENSION COMMENT = 'storage_type',
    kpi_cost_010.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_010.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_010.service_type_kpi_cost_010 AS DIMENSION COMMENT = 'service_type',
    kpi_cost_011.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_011.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_011.none_kpi_cost_011 AS DIMENSION COMMENT = 'none',
    kpi_cost_012.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_012.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_012.none_kpi_cost_012 AS DIMENSION COMMENT = 'none',
    kpi_cost_013.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_013.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_013.none_kpi_cost_013 AS DIMENSION COMMENT = 'none',
    kpi_cost_015.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_015.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_015.none_kpi_cost_015 AS DIMENSION COMMENT = 'none',
    kpi_cost_020.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_cost_020.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_cost_020.none_kpi_cost_020 AS DIMENSION COMMENT = 'none'
  )
  METRICS (
    kpi_cost_001.credits_by_account__warehouse_and_day AS SUM(VALUE)
      COMMENT = 'KPI-COST-001 [credits] Credits billed per warehouse and day: compute + cloud services credits from WAREHOUSE_METERING_HISTORY, with the account-day cloud-services adjustment from METERING_DAILY_HISTORY allocated pro rata to cloud-services use.',
    kpi_cost_002.spend_____by_warehouse_and_day AS SUM(VALUE)
      COMMENT = 'KPI-COST-002 [usd] KPI-COST-001 credits billed multiplied by the contract price per credit (client input).',
    kpi_cost_003.cost_by_cost_centre AS SUM(VALUE)
      COMMENT = 'KPI-COST-003 [usd] Daily billed cost ($) by cost centre: warehouse spend by the warehouses cost-centre tag; serverless, AI and untagged warehouse spend fall into UNALLOCATED. Sums to total billed spend (KPI-COST-011).',
    kpi_cost_004.month_on_month_spend_trend AS MAX(VALUE)
      COMMENT = 'KPI-COST-004 [percent] Percent change in average daily billed spend versus the previous calendar month (average daily spend makes partial months comparable).',
    kpi_cost_005.forecast_vs_budget AS MAX(VALUE)
      COMMENT = 'KPI-COST-005 [ratio] Month-end forecast of billed credits (month-to-date run rate x days in month) divided by the account budgets monthly spending limit (credits). Above 1.0 the month is forecast to overrun.',
    kpi_cost_006.cost_per_query_signature AS SUM(VALUE)
      COMMENT = 'KPI-COST-006 [usd] Compute credits attributed to each parameterised query signature per day, in dollars.',
    kpi_cost_007.idle_credit_share AS AVG(VALUE)
      COMMENT = 'KPI-COST-007 [ratio] compute credits billed while the warehouse had no running queries / total compute credits Target: 0.2 (lower_is_better).',
    kpi_cost_008.serverless_credit_breakdown AS SUM(VALUE)
      COMMENT = 'KPI-COST-008 [credits] Credits per day by serverless service type (clustering, search optimisation, MV refresh, Snowpipe, AI services).',
    kpi_cost_009.storage_by_type AS AVG(VALUE)
      COMMENT = 'KPI-COST-009 [tb] Average stored terabytes per day by storage type (database, stage, fail-safe, hybrid).',
    kpi_cost_010.credits_billed_by_service_type_and_day AS SUM(VALUE)
      COMMENT = 'KPI-COST-010 [credits] Billing truth — METERING_DAILY_HISTORY credits billed per service type and day.',
    kpi_cost_011.total_spend_____by_account_and_day AS SUM(VALUE)
      COMMENT = 'KPI-COST-011 [usd] All billed credits (every service type) for the account-day multiplied by the contract price.',
    kpi_cost_012.storage_cost_per_month AS MAX(VALUE)
      COMMENT = 'KPI-COST-012 [usd] Average stored TB (database + stage + fail-safe + hybrid) in the month x contract storage price per TB-month.',
    kpi_cost_013.capacity_commitment_burn_down AS MAX(VALUE)
      COMMENT = 'KPI-COST-013 [ratio] Cumulative billed credits since the commitment start / annual committed credits, per day; compare with EXPECTED_SHARE (elapsed share of the commitment term).',
    kpi_cost_015.cloud_services_ratio AS AVG(VALUE)
      COMMENT = 'KPI-COST-015 [ratio] Cloud-services credits used / compute credits used for warehouse metering, per account and day.',
    kpi_cost_020.resource_monitor_coverage AS MAX(VALUE)
      COMMENT = 'KPI-COST-020 [ratio] Share of warehouses with a resource monitor attached, per snapshot day.'
  )
  COMMENT = 'Certified cost KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_GOVERNANCE
  TABLES (
    kpi_gov_001 AS OBS.KPI.KPI_GOV_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('tag coverage', 'tagged tables', 'tagging', 'classification coverage')
      COMMENT = 'Tag coverage',
    kpi_gov_002 AS OBS.KPI.KPI_GOV_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('owner coverage', 'ownership', 'data owner', 'tier 1 owners', 'stewardship')
      COMMENT = 'Owner coverage on Tier-1 objects',
    kpi_gov_003 AS OBS.KPI.KPI_GOV_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('masking', 'masking coverage', 'pii', 'sensitive columns', 'data protection')
      COMMENT = 'Masking coverage on classified columns',
    kpi_gov_004 AS OBS.KPI.KPI_GOV_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('dmf', 'data metric functions', 'data quality coverage', 'dq coverage', 'quality monitoring')
      COMMENT = 'DMF coverage on Tier-1 tables',
    kpi_gov_005 AS OBS.KPI.KPI_GOV_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('data quality', 'dq violations', 'quality issues', 'expectation violations')
      COMMENT = 'Data quality expectation violations',
    kpi_gov_006 AS OBS.KPI.KPI_GOV_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('comments', 'column comments', 'documentation', 'described columns')
      COMMENT = 'Tier-1 column comment coverage',
    kpi_gov_007 AS OBS.KPI.KPI_GOV_007
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('table comments', 'described tables')
      COMMENT = 'Table comment coverage',
    kpi_gov_008 AS OBS.KPI.KPI_GOV_008
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('dmf pass rate', 'quality pass rate', 'data quality score')
      COMMENT = 'DMF pass rate',
    kpi_gov_010 AS OBS.KPI.KPI_GOV_010
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('classified columns', 'pii columns', 'sensitive data inventory')
      COMMENT = 'Classified columns'
  )
  DIMENSIONS (
    kpi_gov_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_001.none_kpi_gov_001 AS DIMENSION COMMENT = 'none',
    kpi_gov_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_002.none_kpi_gov_002 AS DIMENSION COMMENT = 'none',
    kpi_gov_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_003.none_kpi_gov_003 AS DIMENSION COMMENT = 'none',
    kpi_gov_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_004.none_kpi_gov_004 AS DIMENSION COMMENT = 'none',
    kpi_gov_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_005.none_kpi_gov_005 AS DIMENSION COMMENT = 'none',
    kpi_gov_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_006.none_kpi_gov_006 AS DIMENSION COMMENT = 'none',
    kpi_gov_007.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_007.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_007.none_kpi_gov_007 AS DIMENSION COMMENT = 'none',
    kpi_gov_008.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_008.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_008.none_kpi_gov_008 AS DIMENSION COMMENT = 'none',
    kpi_gov_010.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_gov_010.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_gov_010.none_kpi_gov_010 AS DIMENSION COMMENT = 'none'
  )
  METRICS (
    kpi_gov_001.tag_coverage AS MAX(VALUE)
      COMMENT = 'KPI-GOV-001 [ratio] Share of tables carrying at least one object-level tag, per snapshot day. Target: 0.9 (higher_is_better).',
    kpi_gov_002.owner_coverage_on_tier_1_objects AS MAX(VALUE)
      COMMENT = 'KPI-GOV-002 [ratio] Share of Tier-1 tables (TIER tag = tier1) carrying the owner tag, per snapshot day. Target: 1 (higher_is_better).',
    kpi_gov_003.masking_coverage_on_classified_columns AS MAX(VALUE)
      COMMENT = 'KPI-GOV-003 [ratio] Share of PII-tagged columns with an active masking policy, per snapshot day. Target: 1 (higher_is_better).',
    kpi_gov_004.dmf_coverage_on_tier_1_tables AS MAX(VALUE)
      COMMENT = 'KPI-GOV-004 [ratio] Share of Tier-1 tables with at least one data metric function attached, per snapshot day. Target: 1 (higher_is_better).',
    kpi_gov_005.data_quality_expectation_violations AS SUM(VALUE)
      COMMENT = 'KPI-GOV-005 [violations] Number of data metric function results that violated their expectation, per account and day.',
    kpi_gov_006.tier_1_column_comment_coverage AS MAX(VALUE)
      COMMENT = 'KPI-GOV-006 [ratio] Share of columns on Tier-1 tables with a comment, per snapshot day.',
    kpi_gov_007.table_comment_coverage AS MAX(VALUE)
      COMMENT = 'KPI-GOV-007 [ratio] Share of tables with a table-level comment, per snapshot day.',
    kpi_gov_008.dmf_pass_rate AS AVG(VALUE)
      COMMENT = 'KPI-GOV-008 [ratio] Share of data metric function results that met their expectation, per account and day.',
    kpi_gov_010.classified_columns AS MAX(VALUE)
      COMMENT = 'KPI-GOV-010 [columns] Number of columns carrying a PII classification tag, per snapshot day.'
  )
  COMMENT = 'Certified governance KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_HEALTH
  TABLES (
    kpi_phi_001 AS OBS.KPI.KPI_PHI_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('health index', 'platform health', 'health score', 'overall health', 'scorecard')
      COMMENT = 'Platform Health Index',
    kpi_phi_002 AS OBS.KPI.KPI_PHI_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('pillar score', 'waf pillar', 'well architected', 'pillar health')
      COMMENT = 'Health Index by WAF pillar'
  )
  DIMENSIONS (
    kpi_phi_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_phi_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_phi_001.none_kpi_phi_001 AS DIMENSION COMMENT = 'none',
    kpi_phi_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_phi_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_phi_002.waf_pillar_kpi_phi_002 AS DIMENSION COMMENT = 'waf_pillar'
  )
  METRICS (
    kpi_phi_001.platform_health_index AS MAX(VALUE)
      COMMENT = 'KPI-PHI-001 [score] 0-100 index: rubric-weighted mean of WAF pillar scores, each the mean attainment of that pillars targeted KPIs (KPI monthly value vs its rubric target, capped at 1).',
    kpi_phi_002.health_index_by_waf_pillar AS MAX(VALUE)
      COMMENT = 'KPI-PHI-002 [score] Pillar scores (0-100) behind KPI-PHI-001, one per Well-Architected pillar and month.'
  )
  COMMENT = 'Certified health KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_PERFORMANCE
  TABLES (
    kpi_perf_001 AS OBS.KPI.KPI_PERF_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('query time', 'latency', 'p95', 'p50', 'median query time', 'slow queries')
      COMMENT = 'Query time p50 / p95 by warehouse',
    kpi_perf_002 AS OBS.KPI.KPI_PERF_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('queued', 'queueing', 'queue time', 'waiting', 'concurrency', 'overload')
      COMMENT = 'Queued time by warehouse',
    kpi_perf_003 AS OBS.KPI.KPI_PERF_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('spill', 'spilling', 'spilled bytes', 'remote spill', 'local spill', 'memory')
      COMMENT = 'Spill to storage',
    kpi_perf_004 AS OBS.KPI.KPI_PERF_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('pruning', 'partition pruning', 'micro partitions', 'scanned partitions', 'clustering effectiveness')
      COMMENT = 'Pruning efficiency',
    kpi_perf_005 AS OBS.KPI.KPI_PERF_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('cache', 'cache hit', 'result cache', 'warehouse cache', 'cache rate')
      COMMENT = 'Cache hit rate',
    kpi_perf_006 AS OBS.KPI.KPI_PERF_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('compilation', 'compile time', 'planning time')
      COMMENT = 'Compilation time p95',
    kpi_perf_007 AS OBS.KPI.KPI_PERF_007
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('regression', 'signature performance', 'query regression', 'slower than usual')
      COMMENT = 'Execution time per query signature',
    kpi_perf_008 AS OBS.KPI.KPI_PERF_008
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('load', 'concurrency', 'utilisation', 'utilization', 'running queries')
      COMMENT = 'Warehouse load (average running)',
    kpi_perf_009 AS OBS.KPI.KPI_PERF_009
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('failed queries', 'query errors', 'error rate')
      COMMENT = 'Failed query rate',
    kpi_perf_011 AS OBS.KPI.KPI_PERF_011
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('long running', 'long queries', 'runaway queries')
      COMMENT = 'Long-running queries'
  )
  DIMENSIONS (
    kpi_perf_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_001.warehouse_kpi_perf_001 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_002.warehouse_kpi_perf_002 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_003.warehouse_kpi_perf_003 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_004.warehouse_kpi_perf_004 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_005.warehouse_kpi_perf_005 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_006.warehouse_kpi_perf_006 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_007.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_007.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_007.query_signature_kpi_perf_007 AS DIMENSION COMMENT = 'query_signature',
    kpi_perf_008.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_008.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_008.warehouse_kpi_perf_008 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_009.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_009.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_009.warehouse_kpi_perf_009 AS DIMENSION COMMENT = 'warehouse',
    kpi_perf_011.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_perf_011.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_perf_011.warehouse_kpi_perf_011 AS DIMENSION COMMENT = 'warehouse'
  )
  METRICS (
    kpi_perf_001.query_time_p50___p95_by_warehouse AS AVG(VALUE)
      COMMENT = 'KPI-PERF-001 [ms] Median and 95th-percentile total elapsed time (ms) of successful queries per warehouse and day; VALUE is p95.',
    kpi_perf_002.queued_time_by_warehouse AS SUM(VALUE)
      COMMENT = 'KPI-PERF-002 [seconds] Total seconds queries spent queued for warehouse overload per warehouse and day. Target: 60 (lower_is_better).',
    kpi_perf_003.spill_to_storage AS SUM(VALUE)
      COMMENT = 'KPI-PERF-003 [gb] Gigabytes spilled to local plus remote storage per warehouse and day. Target: 50 (lower_is_better).',
    kpi_perf_004.pruning_efficiency AS AVG(VALUE)
      COMMENT = 'KPI-PERF-004 [ratio] 1 - partitions scanned / partitions total, over queries that touched partitioned tables, per warehouse and day. Target: 0.8 (higher_is_better).',
    kpi_perf_005.cache_hit_rate AS AVG(VALUE)
      COMMENT = 'KPI-PERF-005 [ratio] Average share of scanned data served from the warehouse cache (PERCENTAGE_SCANNED_FROM_CACHE) per warehouse and day. Target: 0.2 (higher_is_better).',
    kpi_perf_006.compilation_time_p95 AS AVG(VALUE)
      COMMENT = 'KPI-PERF-006 [ms] 95th-percentile compilation time (ms) per warehouse and day.',
    kpi_perf_007.execution_time_per_query_signature AS AVG(VALUE)
      COMMENT = 'KPI-PERF-007 [ms] Average execution time (ms) per parameterised query signature and day — the series the regression alert compares against its forecast band.',
    kpi_perf_008.warehouse_load__average_running_ AS AVG(VALUE)
      COMMENT = 'KPI-PERF-008 [queries] Average number of running queries per active hour, per warehouse and day (WAREHOUSE_LOAD_HISTORY).',
    kpi_perf_009.failed_query_rate AS AVG(VALUE)
      COMMENT = 'KPI-PERF-009 [ratio] Share of queries that did not succeed, per warehouse and day.',
    kpi_perf_011.long_running_queries AS SUM(VALUE)
      COMMENT = 'KPI-PERF-011 [queries] Number of queries whose elapsed time exceeds the rubric long-query limit, per warehouse and day.'
  )
  COMMENT = 'Certified performance KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_RELIABILITY
  TABLES (
    kpi_rel_001 AS OBS.KPI.KPI_REL_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('task success', 'task success rate', 'pipeline success', 'job success', 'task reliability')
      COMMENT = 'Task success rate',
    kpi_rel_002 AS OBS.KPI.KPI_REL_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('failed tasks', 'task failures', 'broken pipelines', 'failed jobs', 'failures')
      COMMENT = 'Failed tasks (24h)',
    kpi_rel_003 AS OBS.KPI.KPI_REL_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('freshness', 'sla', 'late data', 'freshness sla', 'on time', 'data late')
      COMMENT = 'Freshness SLA attainment',
    kpi_rel_004 AS OBS.KPI.KPI_REL_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('harvest', 'harvest success', 'observability pipeline', 'telemetry collection')
      COMMENT = 'Harvest success rate',
    kpi_rel_005 AS OBS.KPI.KPI_REL_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('copy errors', 'load errors', 'snowpipe errors', 'file load failures')
      COMMENT = 'File load error rate',
    kpi_rel_010 AS OBS.KPI.KPI_REL_010
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('retries', 'retried tasks', 'flaky tasks')
      COMMENT = 'Task retries',
    kpi_rel_011 AS OBS.KPI.KPI_REL_011
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('replication', 'failover', 'disaster recovery', 'dr')
      COMMENT = 'Replication / failover groups'
  )
  DIMENSIONS (
    kpi_rel_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_001.none_kpi_rel_001 AS DIMENSION COMMENT = 'none',
    kpi_rel_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_002.none_kpi_rel_002 AS DIMENSION COMMENT = 'none',
    kpi_rel_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_003.table_kpi_rel_003 AS DIMENSION COMMENT = 'table',
    kpi_rel_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_004.none_kpi_rel_004 AS DIMENSION COMMENT = 'none',
    kpi_rel_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_005.table_kpi_rel_005 AS DIMENSION COMMENT = 'table',
    kpi_rel_010.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_010.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_010.none_kpi_rel_010 AS DIMENSION COMMENT = 'none',
    kpi_rel_011.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_rel_011.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_rel_011.none_kpi_rel_011 AS DIMENSION COMMENT = 'none'
  )
  METRICS (
    kpi_rel_001.task_success_rate AS AVG(VALUE)
      COMMENT = 'KPI-REL-001 [ratio] Succeeded task runs / all task runs (failed and skipped runs count as unsuccessful) per account and day. Target: 0.98 (higher_is_better).',
    kpi_rel_002.failed_tasks__24h_ AS SUM(VALUE)
      COMMENT = 'KPI-REL-002 [runs] Number of failed task runs per account and day; FAILED_TIER1 counts tasks loading Tier-1 tables.',
    kpi_rel_003.freshness_sla_attainment AS AVG(VALUE)
      COMMENT = 'KPI-REL-003 [ratio] 1 when the tables loading task succeeded before the clients daily deadline, else 0; averaged over a window it is the attainment rate. Target: 0.95 (higher_is_better).',
    kpi_rel_004.harvest_success_rate AS AVG(VALUE)
      COMMENT = 'KPI-REL-004 [ratio] Successful (or intentionally skipped) harvest steps / all harvest steps per account and day (Section 7.8 target ≥ 99%). Target: 0.99 (higher_is_better).',
    kpi_rel_005.file_load_error_rate AS AVG(VALUE)
      COMMENT = 'KPI-REL-005 [ratio] Share of files loaded by COPY / Snowpipe with a status other than Loaded, per target table and day.',
    kpi_rel_010.task_retries AS SUM(VALUE)
      COMMENT = 'KPI-REL-010 [runs] Number of task runs that needed more than one attempt, per account and day.',
    kpi_rel_011.replication___failover_groups AS MAX(VALUE)
      COMMENT = 'KPI-REL-011 [groups] Number of replication or failover groups configured, per snapshot day.'
  )
  COMMENT = 'Certified reliability KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_SECURITY
  TABLES (
    kpi_sec_001 AS OBS.KPI.KPI_SEC_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('mfa', 'multi factor', '2fa', 'mfa coverage', 'two factor')
      COMMENT = 'MFA coverage',
    kpi_sec_002 AS OBS.KPI.KPI_SEC_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('accountadmin', 'account admin', 'admins', 'privileged users', 'administrators')
      COMMENT = 'ACCOUNTADMIN grantees',
    kpi_sec_003 AS OBS.KPI.KPI_SEC_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('failed logins', 'login failures', 'brute force', 'authentication failures')
      COMMENT = 'Failed logins',
    kpi_sec_004 AS OBS.KPI.KPI_SEC_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('dormant', 'inactive users', 'stale users', 'unused accounts')
      COMMENT = 'Dormant users',
    kpi_sec_005 AS OBS.KPI.KPI_SEC_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('network policy', 'ip allow list', 'network rules', 'network coverage')
      COMMENT = 'Network-policy coverage',
    kpi_sec_006 AS OBS.KPI.KPI_SEC_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('without mfa', 'no mfa', 'users missing mfa', 'unprotected users')
      COMMENT = 'Human users without MFA',
    kpi_sec_007 AS OBS.KPI.KPI_SEC_007
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('accountadmin use', 'admin activity', 'privileged activity', 'break glass')
      COMMENT = 'ACCOUNTADMIN activity',
    kpi_sec_008 AS OBS.KPI.KPI_SEC_008
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('service users', 'service accounts', 'password service users', 'legacy service')
      COMMENT = 'Service users with passwords',
    kpi_sec_010 AS OBS.KPI.KPI_SEC_010
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('orphan roles', 'unused roles', 'role cleanup')
      COMMENT = 'Orphan roles',
    kpi_sec_012 AS OBS.KPI.KPI_SEC_012
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('login failure rate', 'failed login share')
      COMMENT = 'Failed login share'
  )
  DIMENSIONS (
    kpi_sec_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_001.none_kpi_sec_001 AS DIMENSION COMMENT = 'none',
    kpi_sec_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_002.none_kpi_sec_002 AS DIMENSION COMMENT = 'none',
    kpi_sec_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_003.none_kpi_sec_003 AS DIMENSION COMMENT = 'none',
    kpi_sec_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_004.none_kpi_sec_004 AS DIMENSION COMMENT = 'none',
    kpi_sec_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_005.none_kpi_sec_005 AS DIMENSION COMMENT = 'none',
    kpi_sec_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_006.none_kpi_sec_006 AS DIMENSION COMMENT = 'none',
    kpi_sec_007.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_007.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_007.none_kpi_sec_007 AS DIMENSION COMMENT = 'none',
    kpi_sec_008.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_008.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_008.none_kpi_sec_008 AS DIMENSION COMMENT = 'none',
    kpi_sec_010.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_010.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_010.none_kpi_sec_010 AS DIMENSION COMMENT = 'none',
    kpi_sec_012.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_sec_012.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_sec_012.none_kpi_sec_012 AS DIMENSION COMMENT = 'none'
  )
  METRICS (
    kpi_sec_001.mfa_coverage AS MAX(VALUE)
      COMMENT = 'KPI-SEC-001 [ratio] Share of enabled human users protected by MFA: HAS_MFA, or SSO-only users without a password (MFA enforced by the identity provider). Target: 1 (higher_is_better).',
    kpi_sec_002.accountadmin_grantees AS MAX(VALUE)
      COMMENT = 'KPI-SEC-002 [users] Number of users granted the ACCOUNTADMIN role, per snapshot day. Target: 3 (lower_is_better).',
    kpi_sec_003.failed_logins AS SUM(VALUE)
      COMMENT = 'KPI-SEC-003 [logins] Number of failed login attempts per account and day.',
    kpi_sec_004.dormant_users AS MAX(VALUE)
      COMMENT = 'KPI-SEC-004 [users] Enabled human users with no successful login within the rubric dormancy window, per snapshot day. Target: 0 (lower_is_better).',
    kpi_sec_005.network_policy_coverage AS MAX(VALUE)
      COMMENT = 'KPI-SEC-005 [ratio] 1.0 when an account-level network policy is set; otherwise the share of users with a user-level network policy. Target: 1 (higher_is_better).',
    kpi_sec_006.human_users_without_mfa AS MAX(VALUE)
      COMMENT = 'KPI-SEC-006 [users] Number of enabled human users not protected by MFA (complement of KPI-SEC-001), per snapshot day.',
    kpi_sec_007.accountadmin_activity AS SUM(VALUE)
      COMMENT = 'KPI-SEC-007 [queries] Queries executed under the ACCOUNTADMIN role per account and day (USERS = distinct users).',
    kpi_sec_008.service_users_with_passwords AS MAX(VALUE)
      COMMENT = 'KPI-SEC-008 [users] Service (or legacy service) users that still authenticate with a password, per snapshot day.',
    kpi_sec_010.orphan_roles AS MAX(VALUE)
      COMMENT = 'KPI-SEC-010 [roles] Non-system roles granted to no user and no role (current snapshot).',
    kpi_sec_012.failed_login_share AS AVG(VALUE)
      COMMENT = 'KPI-SEC-012 [ratio] Failed login attempts / all login attempts per account and day.'
  )
  COMMENT = 'Certified security KPIs (Package O semantic layer)';

CREATE OR REPLACE SEMANTIC VIEW OBS.SEMANTIC.SV_USAGE
  TABLES (
    kpi_use_001 AS OBS.KPI.KPI_USE_001
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('active users', 'users', 'daily active users', 'dau', 'adoption', 'how many users')
      COMMENT = 'Active users',
    kpi_use_002 AS OBS.KPI.KPI_USE_002
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('client tool', 'tools', 'applications', 'power bi', 'dbt', 'drivers')
      COMMENT = 'Queries by client tool',
    kpi_use_003 AS OBS.KPI.KPI_USE_003
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('unused', 'unused tables', 'stale objects', 'unaccessed tables', 'dead tables')
      COMMENT = 'Unused objects',
    kpi_use_004 AS OBS.KPI.KPI_USE_004
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('query volume', 'number of queries', 'query count', 'how many queries', 'workload')
      COMMENT = 'Query volume by warehouse',
    kpi_use_005 AS OBS.KPI.KPI_USE_005
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('top consumers', 'top users', 'heaviest users', 'who uses the most', 'biggest spenders')
      COMMENT = 'Top consumers',
    kpi_use_006 AS OBS.KPI.KPI_USE_006
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('adoption by domain', 'domain adoption', 'schema usage')
      COMMENT = 'Adoption by domain',
    kpi_use_007 AS OBS.KPI.KPI_USE_007
      PRIMARY KEY (ACCOUNT_NAME, PERIOD, DIMENSION)
      WITH SYNONYMS ('report views', 'dashboard views', 'bi usage', 'report usage')
      COMMENT = 'BI report views (90 days)'
  )
  DIMENSIONS (
    kpi_use_001.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_001.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_001.none_kpi_use_001 AS DIMENSION COMMENT = 'none',
    kpi_use_002.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_002.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_002.client_tool_kpi_use_002 AS DIMENSION COMMENT = 'client_tool',
    kpi_use_003.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_003.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_003.none_kpi_use_003 AS DIMENSION COMMENT = 'none',
    kpi_use_004.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_004.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_004.warehouse_kpi_use_004 AS DIMENSION COMMENT = 'warehouse',
    kpi_use_005.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_005.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_005.user_kpi_use_005 AS DIMENSION COMMENT = 'user',
    kpi_use_006.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_006.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_006.data_domain_kpi_use_006 AS DIMENSION COMMENT = 'data_domain',
    kpi_use_007.account_name AS ACCOUNT_NAME COMMENT = 'Snowflake account',
    kpi_use_007.period AS PERIOD COMMENT = 'Day (or month) of the KPI value',
    kpi_use_007.report_kpi_use_007 AS DIMENSION COMMENT = 'report'
  )
  METRICS (
    kpi_use_001.active_users AS AVG(VALUE)
      COMMENT = 'KPI-USE-001 [users] Distinct users who ran at least one query, per account and day (HUMAN_USERS excludes service users).',
    kpi_use_002.queries_by_client_tool AS SUM(VALUE)
      COMMENT = 'KPI-USE-002 [queries] Number of queries per client application (driver / tool) and day.',
    kpi_use_003.unused_objects AS MAX(VALUE)
      COMMENT = 'KPI-USE-003 [tables] Tables with no recorded access within the rubric window before the snapshot day. Target: 0 (lower_is_better).',
    kpi_use_004.query_volume_by_warehouse AS SUM(VALUE)
      COMMENT = 'KPI-USE-004 [queries] Number of queries per warehouse and day.',
    kpi_use_005.top_consumers AS SUM(VALUE)
      COMMENT = 'KPI-USE-005 [credits] Compute credits attributed to each user per day (top consumers).',
    kpi_use_006.adoption_by_domain AS AVG(VALUE)
      COMMENT = 'KPI-USE-006 [users] Distinct users reading objects in each database schema (data domain) per day.',
    kpi_use_007.bi_report_views__90_days_ AS MAX(VALUE)
      COMMENT = 'KPI-USE-007 [views] Views in the last 90 days per BI report, per snapshot day (BI metadata).'
  )
  COMMENT = 'Certified usage KPIs (Package O semantic layer)';
