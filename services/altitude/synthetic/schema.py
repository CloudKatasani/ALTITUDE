"""Harvest contract: evidence tables captured into a diagnostic snapshot.

Keys are snapshot table names. ``source`` documents where a live harvest reads
from (verify view names / edition requirements per engagement — Section 6.3).
Column names follow Snowflake's ACCOUNT_USAGE naming.
"""

from __future__ import annotations

HARVEST_SCHEMA: dict[str, dict] = {
    "ACCOUNT_INFO": {
        "source": "CURRENT_ACCOUNT(), CURRENT_REGION(), SYSTEM$... (client input for edition)",
        "columns": {"ACCOUNT_NAME": "VARCHAR", "ORGANIZATION_NAME": "VARCHAR", "REGION": "VARCHAR",
                    "EDITION": "VARCHAR", "ACCOUNT_LOCATOR": "VARCHAR", "NETWORK_POLICY": "VARCHAR"},
    },
    "CLIENT_INPUTS": {
        "source": "engagement intake (contract price, commitments, tiers, SLAs) — client supplied",
        "columns": {"KEY": "VARCHAR", "VALUE": "JSON"},
    },
    "WAREHOUSES": {
        "source": "SHOW WAREHOUSES + TAG_REFERENCES (domain=WAREHOUSE)",
        "columns": {"WAREHOUSE_NAME": "VARCHAR", "WAREHOUSE_SIZE": "VARCHAR", "AUTO_SUSPEND": "INTEGER",
                    "AUTO_RESUME": "BOOLEAN", "MIN_CLUSTER_COUNT": "INTEGER", "MAX_CLUSTER_COUNT": "INTEGER",
                    "SCALING_POLICY": "VARCHAR", "RESOURCE_MONITOR": "VARCHAR", "OWNER": "VARCHAR",
                    "COMMENT": "VARCHAR", "STATEMENT_TIMEOUT_IN_SECONDS": "INTEGER", "WORKLOAD_CLASS": "VARCHAR"},
    },
    "RESOURCE_MONITORS": {
        "source": "SHOW RESOURCE MONITORS",
        "columns": {"NAME": "VARCHAR", "CREDIT_QUOTA": "DOUBLE", "LEVEL": "VARCHAR", "WAREHOUSES": "VARCHAR",
                    "NOTIFY_AT": "VARCHAR", "SUSPEND_AT": "INTEGER"},
    },
    "WAREHOUSE_METERING_HISTORY": {
        "source": "ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "WAREHOUSE_ID": "INTEGER",
                    "WAREHOUSE_NAME": "VARCHAR", "CREDITS_USED": "DOUBLE", "CREDITS_USED_COMPUTE": "DOUBLE",
                    "CREDITS_USED_CLOUD_SERVICES": "DOUBLE"},
    },
    "WAREHOUSE_LOAD_HISTORY": {
        "source": "ACCOUNT_USAGE.WAREHOUSE_LOAD_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "WAREHOUSE_NAME": "VARCHAR",
                    "AVG_RUNNING": "DOUBLE", "AVG_QUEUED_LOAD": "DOUBLE", "AVG_QUEUED_PROVISIONING": "DOUBLE",
                    "AVG_BLOCKED": "DOUBLE"},
    },
    "METERING_DAILY_HISTORY": {
        "source": "ACCOUNT_USAGE.METERING_DAILY_HISTORY",
        "columns": {"USAGE_DATE": "DATE", "SERVICE_TYPE": "VARCHAR", "CREDITS_USED_COMPUTE": "DOUBLE",
                    "CREDITS_USED_CLOUD_SERVICES": "DOUBLE", "CREDITS_USED": "DOUBLE",
                    "CREDITS_ADJUSTMENT_CLOUD_SERVICES": "DOUBLE", "CREDITS_BILLED": "DOUBLE"},
    },
    "QUERY_HISTORY": {
        "source": "ACCOUNT_USAGE.QUERY_HISTORY",
        "columns": {"QUERY_ID": "VARCHAR", "QUERY_TEXT": "VARCHAR", "QUERY_PARAMETERIZED_HASH": "VARCHAR",
                    "QUERY_TYPE": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR",
                    "USER_NAME": "VARCHAR", "ROLE_NAME": "VARCHAR", "WAREHOUSE_NAME": "VARCHAR",
                    "WAREHOUSE_SIZE": "VARCHAR", "QUERY_TAG": "VARCHAR", "EXECUTION_STATUS": "VARCHAR",
                    "ERROR_MESSAGE": "VARCHAR", "START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP",
                    "TOTAL_ELAPSED_TIME": "BIGINT", "EXECUTION_TIME": "BIGINT", "QUEUED_OVERLOAD_TIME": "BIGINT",
                    "COMPILATION_TIME": "BIGINT", "BYTES_SCANNED": "BIGINT", "PERCENTAGE_SCANNED_FROM_CACHE": "DOUBLE",
                    "BYTES_WRITTEN": "BIGINT", "ROWS_PRODUCED": "BIGINT", "ROWS_INSERTED": "BIGINT",
                    "PARTITIONS_SCANNED": "BIGINT", "PARTITIONS_TOTAL": "BIGINT",
                    "BYTES_SPILLED_TO_LOCAL_STORAGE": "BIGINT", "BYTES_SPILLED_TO_REMOTE_STORAGE": "BIGINT",
                    "CREDITS_USED_CLOUD_SERVICES": "DOUBLE", "CLIENT_APPLICATION_ID": "VARCHAR"},
    },
    "QUERY_ATTRIBUTION_HISTORY": {
        "source": "ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY",
        "columns": {"QUERY_ID": "VARCHAR", "WAREHOUSE_NAME": "VARCHAR", "QUERY_PARAMETERIZED_HASH": "VARCHAR",
                    "QUERY_TAG": "VARCHAR", "USER_NAME": "VARCHAR", "START_TIME": "TIMESTAMP",
                    "END_TIME": "TIMESTAMP", "CREDITS_ATTRIBUTED_COMPUTE": "DOUBLE"},
    },
    "ACCESS_HISTORY": {
        "source": "ACCOUNT_USAGE.ACCESS_HISTORY (flattened BASE_OBJECTS_ACCESSED / OBJECTS_MODIFIED; Enterprise+)",
        "columns": {"QUERY_ID": "VARCHAR", "QUERY_START_TIME": "TIMESTAMP", "USER_NAME": "VARCHAR",
                    "OBJECT_NAME": "VARCHAR", "OBJECT_DOMAIN": "VARCHAR", "ACCESS_TYPE": "VARCHAR"},
    },
    "AUTOMATIC_CLUSTERING_HISTORY": {
        "source": "ACCOUNT_USAGE.AUTOMATIC_CLUSTERING_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "TABLE_NAME": "VARCHAR",
                    "CREDITS_USED": "DOUBLE", "NUM_BYTES_RECLUSTERED": "BIGINT", "NUM_ROWS_RECLUSTERED": "BIGINT"},
    },
    "SEARCH_OPTIMIZATION_HISTORY": {
        "source": "ACCOUNT_USAGE.SEARCH_OPTIMIZATION_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "TABLE_NAME": "VARCHAR",
                    "CREDITS_USED": "DOUBLE"},
    },
    "MATERIALIZED_VIEW_REFRESH_HISTORY": {
        "source": "ACCOUNT_USAGE.MATERIALIZED_VIEW_REFRESH_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "TABLE_NAME": "VARCHAR",
                    "CREDITS_USED": "DOUBLE"},
    },
    "STORAGE_USAGE": {
        "source": "ACCOUNT_USAGE.STORAGE_USAGE",
        "columns": {"USAGE_DATE": "DATE", "STORAGE_BYTES": "BIGINT", "STAGE_BYTES": "BIGINT",
                    "FAILSAFE_BYTES": "BIGINT", "HYBRID_TABLE_STORAGE_BYTES": "BIGINT"},
    },
    "TABLES": {
        "source": "ACCOUNT_USAGE.TABLES (deleted IS NULL) + SHOW TABLES clustering_key",
        "columns": {"TABLE_ID": "INTEGER", "TABLE_CATALOG": "VARCHAR", "TABLE_SCHEMA": "VARCHAR",
                    "TABLE_NAME": "VARCHAR", "FQ_NAME": "VARCHAR", "TABLE_TYPE": "VARCHAR", "IS_TRANSIENT": "BOOLEAN",
                    "IS_ICEBERG": "BOOLEAN", "CLUSTERING_KEY": "VARCHAR", "ROW_COUNT": "BIGINT", "BYTES": "BIGINT",
                    "RETENTION_TIME": "INTEGER", "CREATED": "TIMESTAMP", "LAST_ALTERED": "TIMESTAMP",
                    "LAST_DDL": "TIMESTAMP", "TABLE_OWNER": "VARCHAR", "COMMENT": "VARCHAR",
                    "CLONE_GROUP_ID": "INTEGER", "COLUMN_SIGNATURE": "VARCHAR"},
    },
    "TABLE_STORAGE_METRICS": {
        "source": "ACCOUNT_USAGE.TABLE_STORAGE_METRICS",
        "columns": {"ID": "INTEGER", "TABLE_CATALOG": "VARCHAR", "TABLE_SCHEMA": "VARCHAR", "TABLE_NAME": "VARCHAR",
                    "FQ_NAME": "VARCHAR", "IS_TRANSIENT": "BOOLEAN", "ACTIVE_BYTES": "BIGINT",
                    "TIME_TRAVEL_BYTES": "BIGINT", "FAILSAFE_BYTES": "BIGINT", "RETAINED_FOR_CLONE_BYTES": "BIGINT",
                    "DELETED": "BOOLEAN", "CLONE_GROUP_ID": "INTEGER"},
    },
    "COLUMNS": {
        "source": "ACCOUNT_USAGE.COLUMNS (deleted IS NULL)",
        "columns": {"TABLE_CATALOG": "VARCHAR", "TABLE_SCHEMA": "VARCHAR", "TABLE_NAME": "VARCHAR",
                    "FQ_NAME": "VARCHAR", "COLUMN_NAME": "VARCHAR", "ORDINAL_POSITION": "INTEGER",
                    "DATA_TYPE": "VARCHAR", "IS_NULLABLE": "VARCHAR", "COMMENT": "VARCHAR"},
    },
    "VIEWS": {
        "source": "ACCOUNT_USAGE.VIEWS",
        "columns": {"TABLE_CATALOG": "VARCHAR", "TABLE_SCHEMA": "VARCHAR", "TABLE_NAME": "VARCHAR",
                    "FQ_NAME": "VARCHAR", "VIEW_DEFINITION": "VARCHAR", "IS_SECURE": "BOOLEAN", "COMMENT": "VARCHAR"},
    },
    "OBJECT_DEPENDENCIES": {
        "source": "ACCOUNT_USAGE.OBJECT_DEPENDENCIES",
        "columns": {"REFERENCING_OBJECT_NAME": "VARCHAR", "REFERENCING_OBJECT_DOMAIN": "VARCHAR",
                    "REFERENCED_OBJECT_NAME": "VARCHAR", "REFERENCED_OBJECT_DOMAIN": "VARCHAR",
                    "DEPENDENCY_TYPE": "VARCHAR"},
    },
    "TASKS": {
        "source": "SHOW TASKS IN ACCOUNT",
        "columns": {"TASK_NAME": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR",
                    "FQ_NAME": "VARCHAR", "OWNER": "VARCHAR", "WAREHOUSE": "VARCHAR", "SCHEDULE": "VARCHAR",
                    "PREDECESSORS": "VARCHAR", "STATE": "VARCHAR", "TARGET_TABLE": "VARCHAR", "DEFINITION": "VARCHAR"},
    },
    "TASK_HISTORY": {
        "source": "ACCOUNT_USAGE.TASK_HISTORY",
        "columns": {"NAME": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR", "FQ_NAME": "VARCHAR",
                    "STATE": "VARCHAR", "ERROR_CODE": "VARCHAR", "ERROR_MESSAGE": "VARCHAR",
                    "SCHEDULED_TIME": "TIMESTAMP", "QUERY_START_TIME": "TIMESTAMP", "COMPLETED_TIME": "TIMESTAMP",
                    "ROOT_TASK_ID": "VARCHAR", "RUN_ID": "VARCHAR", "ATTEMPT_NUMBER": "INTEGER", "QUERY_ID": "VARCHAR"},
    },
    "COPY_HISTORY": {
        "source": "ACCOUNT_USAGE.COPY_HISTORY",
        "columns": {"FILE_NAME": "VARCHAR", "TABLE_NAME": "VARCHAR", "PIPE_NAME": "VARCHAR",
                    "LAST_LOAD_TIME": "TIMESTAMP", "ROW_COUNT": "BIGINT", "ERROR_COUNT": "BIGINT", "STATUS": "VARCHAR"},
    },
    "PIPE_USAGE_HISTORY": {
        "source": "ACCOUNT_USAGE.PIPE_USAGE_HISTORY",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "PIPE_NAME": "VARCHAR",
                    "CREDITS_USED": "DOUBLE", "BYTES_INSERTED": "BIGINT", "FILES_INSERTED": "BIGINT"},
    },
    "REPLICATION_GROUPS": {
        "source": "SHOW REPLICATION GROUPS / FAILOVER GROUPS",
        "columns": {"NAME": "VARCHAR", "TYPE": "VARCHAR", "OBJECT_TYPES": "VARCHAR", "ALLOWED_DATABASES": "VARCHAR",
                    "REPLICATION_SCHEDULE": "VARCHAR", "IS_PRIMARY": "BOOLEAN"},
    },
    "USERS": {
        "source": "ACCOUNT_USAGE.USERS (deleted_on IS NULL)",
        "columns": {"NAME": "VARCHAR", "TYPE": "VARCHAR", "LOGIN_NAME": "VARCHAR", "DEFAULT_ROLE": "VARCHAR",
                    "HAS_PASSWORD": "BOOLEAN", "HAS_MFA": "BOOLEAN", "HAS_RSA_PUBLIC_KEY": "BOOLEAN",
                    "EXT_AUTHN_UID": "VARCHAR", "DISABLED": "BOOLEAN", "CREATED_ON": "TIMESTAMP",
                    "LAST_SUCCESS_LOGIN": "TIMESTAMP", "NETWORK_POLICY": "VARCHAR", "OWNER": "VARCHAR",
                    "COMMENT": "VARCHAR"},
    },
    "ROLES": {
        "source": "ACCOUNT_USAGE.ROLES (deleted_on IS NULL)",
        "columns": {"NAME": "VARCHAR", "ROLE_TYPE": "VARCHAR", "OWNER": "VARCHAR", "COMMENT": "VARCHAR",
                    "CREATED_ON": "TIMESTAMP"},
    },
    "GRANTS_TO_ROLES": {
        "source": "ACCOUNT_USAGE.GRANTS_TO_ROLES (deleted_on IS NULL)",
        "columns": {"PRIVILEGE": "VARCHAR", "GRANTED_ON": "VARCHAR", "NAME": "VARCHAR", "TABLE_CATALOG": "VARCHAR",
                    "TABLE_SCHEMA": "VARCHAR", "GRANTED_TO": "VARCHAR", "GRANTEE_NAME": "VARCHAR",
                    "GRANT_OPTION": "BOOLEAN", "GRANTED_BY": "VARCHAR", "CREATED_ON": "TIMESTAMP"},
    },
    "GRANTS_TO_USERS": {
        "source": "ACCOUNT_USAGE.GRANTS_TO_USERS (deleted_on IS NULL)",
        "columns": {"ROLE": "VARCHAR", "GRANTED_TO": "VARCHAR", "GRANTEE_NAME": "VARCHAR",
                    "GRANTED_BY": "VARCHAR", "CREATED_ON": "TIMESTAMP"},
    },
    "LOGIN_HISTORY": {
        "source": "ACCOUNT_USAGE.LOGIN_HISTORY",
        "columns": {"EVENT_ID": "VARCHAR", "EVENT_TIMESTAMP": "TIMESTAMP", "USER_NAME": "VARCHAR",
                    "CLIENT_IP": "VARCHAR", "REPORTED_CLIENT_TYPE": "VARCHAR",
                    "FIRST_AUTHENTICATION_FACTOR": "VARCHAR", "SECOND_AUTHENTICATION_FACTOR": "VARCHAR",
                    "IS_SUCCESS": "VARCHAR", "ERROR_CODE": "VARCHAR", "ERROR_MESSAGE": "VARCHAR"},
    },
    "NETWORK_POLICIES": {
        "source": "ACCOUNT_USAGE.NETWORK_POLICIES",
        "columns": {"NAME": "VARCHAR", "ALLOWED_IP_LIST": "VARCHAR", "BLOCKED_IP_LIST": "VARCHAR",
                    "ALLOWED_NETWORK_RULE_LIST": "VARCHAR", "OWNER": "VARCHAR"},
    },
    "TAG_REFERENCES": {
        "source": "ACCOUNT_USAGE.TAG_REFERENCES",
        "columns": {"TAG_DATABASE": "VARCHAR", "TAG_SCHEMA": "VARCHAR", "TAG_NAME": "VARCHAR",
                    "TAG_VALUE": "VARCHAR", "OBJECT_DATABASE": "VARCHAR", "OBJECT_SCHEMA": "VARCHAR",
                    "OBJECT_NAME": "VARCHAR", "COLUMN_NAME": "VARCHAR", "DOMAIN": "VARCHAR"},
    },
    "POLICY_REFERENCES": {
        "source": "ACCOUNT_USAGE.POLICY_REFERENCES",
        "columns": {"POLICY_NAME": "VARCHAR", "POLICY_KIND": "VARCHAR", "REF_DATABASE_NAME": "VARCHAR",
                    "REF_SCHEMA_NAME": "VARCHAR", "REF_ENTITY_NAME": "VARCHAR", "REF_ENTITY_DOMAIN": "VARCHAR",
                    "REF_COLUMN_NAME": "VARCHAR", "TAG_NAME": "VARCHAR", "POLICY_STATUS": "VARCHAR"},
    },
    "DATA_METRIC_FUNCTION_REFERENCES": {
        "source": "ACCOUNT_USAGE.DATA_METRIC_FUNCTION_REFERENCES",
        "columns": {"METRIC_DATABASE_NAME": "VARCHAR", "METRIC_NAME": "VARCHAR", "REF_ENTITY_NAME": "VARCHAR",
                    "REF_ENTITY_DOMAIN": "VARCHAR", "SCHEDULE": "VARCHAR", "SCHEDULE_STATUS": "VARCHAR"},
    },
    "DATA_QUALITY_MONITORING_RESULTS": {
        "source": "SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS",
        "columns": {"MEASUREMENT_TIME": "TIMESTAMP", "TABLE_NAME": "VARCHAR", "METRIC_NAME": "VARCHAR",
                    "VALUE": "DOUBLE", "EXPECTATION_VIOLATED": "BOOLEAN"},
    },
    "ALERTS": {
        "source": "SHOW ALERTS IN ACCOUNT",
        "columns": {"NAME": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR", "STATE": "VARCHAR",
                    "CONDITION": "VARCHAR", "ACTION": "VARCHAR", "ALERT_CLASS": "VARCHAR"},
    },
    "BUDGETS": {
        "source": "SNOWFLAKE.CORE.BUDGET instances (SHOW SNOWFLAKE.CORE.BUDGET)",
        "columns": {"NAME": "VARCHAR", "SCOPE": "VARCHAR", "SPENDING_LIMIT": "DOUBLE", "OBJECTS": "VARCHAR"},
    },
    "CORTEX_USAGE_HISTORY": {
        "source": "ACCOUNT_USAGE.CORTEX_FUNCTIONS_USAGE_HISTORY / CORTEX_AGENT_USAGE_HISTORY (joined to QUERY_HISTORY for role)",
        "columns": {"START_TIME": "TIMESTAMP", "END_TIME": "TIMESTAMP", "FUNCTION_NAME": "VARCHAR",
                    "MODEL_NAME": "VARCHAR", "AGENT_NAME": "VARCHAR", "ROLE_NAME": "VARCHAR", "USER_NAME": "VARCHAR",
                    "TOKENS": "BIGINT", "TOKEN_CREDITS": "DOUBLE"},
    },
    "SEMANTIC_VIEWS": {
        "source": "SHOW SEMANTIC VIEWS IN ACCOUNT",
        "columns": {"NAME": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR",
                    "KPI_DOMAIN": "VARCHAR", "COMMENT": "VARCHAR"},
    },
    "CORTEX_SEARCH_SERVICES": {
        "source": "SHOW CORTEX SEARCH SERVICES IN ACCOUNT",
        "columns": {"NAME": "VARCHAR", "DATABASE_NAME": "VARCHAR", "SCHEMA_NAME": "VARCHAR",
                    "SOURCE_TABLE": "VARCHAR", "TARGET_LAG": "VARCHAR"},
    },
    "BI_REPORTS": {
        "source": "BI tool metadata APIs/exports (Power BI scanner, Tableau metadata, ...)",
        "columns": {"REPORT_ID": "VARCHAR", "TOOL": "VARCHAR", "NAME": "VARCHAR", "WORKSPACE": "VARCHAR",
                    "OWNER": "VARCHAR", "DATASET": "VARCHAR", "STRUCTURE_HASH": "VARCHAR",
                    "QUERY_PARAMETERIZED_HASH": "VARCHAR", "VIEWS_90D": "INTEGER", "REFRESHES_PER_DAY": "INTEGER",
                    "LAST_VIEWED": "TIMESTAMP", "CREATED": "TIMESTAMP"},
    },
    "BI_MEASURES": {
        "source": "BI tool semantic model / measure definitions",
        "columns": {"REPORT_ID": "VARCHAR", "KPI_NAME": "VARCHAR", "EXPRESSION": "VARCHAR",
                    "SOURCE_COLUMNS": "VARCHAR"},
    },
}


def columns(table: str) -> dict[str, str]:
    return HARVEST_SCHEMA[table]["columns"]
