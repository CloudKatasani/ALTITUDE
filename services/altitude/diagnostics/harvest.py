"""Live harvester: read-only SELECTs over ``SNOWFLAKE.ACCOUNT_USAGE`` (and SHOW output) → sealed snapshot.

- One query per harvest-contract table (``altitude.synthetic.schema.HARVEST_SCHEMA``); each returns exactly
  the contract columns, so detectors run unchanged on live and synthetic snapshots.
- Works with any DB-API 2.0 connection (``snowflake-connector-python`` is an optional extra; tests use a fake).
- Every statement passes :func:`altitude.diagnostics.readonly.assert_read_only` *before* it reaches the
  connection: only single SELECT / SHOW / DESCRIBE statements are ever sent.
- ``CLIENT_INPUTS`` (contract price, commitments, tiers, SLAs) and BI metadata are supplied by the engagement,
  not queried. A source that cannot be read (edition, missing grant) is recorded as ``unavailable`` in the
  snapshot metadata; the engine then lowers confidence and skips checks that depend on it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from altitude.core.snapshot import Snapshot, SnapshotWriter
from altitude.synthetic.schema import HARVEST_SCHEMA

from .readonly import assert_read_only

AU = "SNOWFLAKE.ACCOUNT_USAGE"
CLIENT_SUPPLIED = {"CLIENT_INPUTS", "BI_REPORTS", "BI_MEASURES"}
WINDOW = "%(window_start)s"
WINDOW_END = "%(window_end)s"


@dataclass(frozen=True)
class HarvestQuery:
    table: str
    sql: str
    database_role: str                 # SNOWFLAKE database role (or privilege) that makes the source readable
    pre: str | None = None             # SHOW statement whose RESULT_SCAN the SELECT reads

    def statements(self) -> list[str]:
        tag = f"/* altitude-harvest:{self.table} */ "
        out = [tag + self.pre] if self.pre else []
        out.append(tag + self.sql)
        return out


def _fq(*parts: str) -> str:
    return " || '.' || ".join(parts)


def _size(col: str) -> str:
    """Normalise SHOW WAREHOUSES sizes (``X-Small``, ``2X-Large``) to the contract's ``XSMALL`` / ``XXLARGE``."""
    pairs = [("X-SMALL", "XSMALL"), ("X-LARGE", "XLARGE"), ("2X-LARGE", "XXLARGE"), ("3X-LARGE", "XXXLARGE"),
             ("4X-LARGE", "X4LARGE")]
    whens = " ".join(f"WHEN '{a}' THEN '{b}'" for a, b in pairs)
    return f"CASE UPPER({col}) {whens} ELSE UPPER(REPLACE({col}, '-', '')) END"


HARVEST_QUERIES: dict[str, HarvestQuery] = {q.table: q for q in [
    HarvestQuery("ACCOUNT_INFO", database_role="(session context)",
                 pre="SHOW PARAMETERS LIKE 'NETWORK_POLICY' IN ACCOUNT",
                 sql="SELECT CURRENT_ACCOUNT_NAME() AS ACCOUNT_NAME, CURRENT_ORGANIZATION_NAME() AS ORGANIZATION_NAME, "
                     "CURRENT_REGION() AS REGION, %(edition)s AS EDITION, CURRENT_ACCOUNT() AS ACCOUNT_LOCATOR, "
                     "NULLIF(MAX(\"value\"), '') AS NETWORK_POLICY FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("WAREHOUSES", database_role="MONITOR USAGE", pre="SHOW WAREHOUSES",
                 sql=f"SELECT w.\"name\" AS WAREHOUSE_NAME, {_size('w.' + chr(34) + 'size' + chr(34))} AS WAREHOUSE_SIZE, "
                     "TRY_TO_NUMBER(w.\"auto_suspend\") AS AUTO_SUSPEND, w.\"auto_resume\" = 'true' AS AUTO_RESUME, "
                     "w.\"min_cluster_count\" AS MIN_CLUSTER_COUNT, w.\"max_cluster_count\" AS MAX_CLUSTER_COUNT, "
                     "w.\"scaling_policy\" AS SCALING_POLICY, NULLIF(w.\"resource_monitor\", 'null') AS RESOURCE_MONITOR, "
                     "w.\"owner\" AS OWNER, w.\"comment\" AS COMMENT, NULL AS STATEMENT_TIMEOUT_IN_SECONDS, "
                     "LOWER(t.TAG_VALUE) AS WORKLOAD_CLASS "
                     "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) w "
                     f"LEFT JOIN {AU}.TAG_REFERENCES t ON t.DOMAIN = 'WAREHOUSE' AND t.OBJECT_NAME = w.\"name\" "
                     "AND t.TAG_NAME = 'WORKLOAD_CLASS' AND t.OBJECT_DELETED IS NULL"),
    HarvestQuery("RESOURCE_MONITORS", database_role="MONITOR USAGE", pre="SHOW RESOURCE MONITORS",
                 sql="SELECT \"name\" AS NAME, TRY_TO_DOUBLE(\"credit_quota\") AS CREDIT_QUOTA, \"level\" AS LEVEL, "
                     "NULL AS WAREHOUSES, \"notify_at\" AS NOTIFY_AT, "
                     "TRY_TO_NUMBER(REPLACE(\"suspend_at\", '%', '')) AS SUSPEND_AT "
                     "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("WAREHOUSE_METERING_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT START_TIME, END_TIME, WAREHOUSE_ID, WAREHOUSE_NAME, CREDITS_USED, CREDITS_USED_COMPUTE, "
                     f"CREDITS_USED_CLOUD_SERVICES FROM {AU}.WAREHOUSE_METERING_HISTORY "
                     f"WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("WAREHOUSE_LOAD_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT START_TIME, END_TIME, WAREHOUSE_NAME, AVG_RUNNING, AVG_QUEUED_LOAD, AVG_QUEUED_PROVISIONING, "
                     f"AVG_BLOCKED FROM {AU}.WAREHOUSE_LOAD_HISTORY "
                     f"WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("METERING_DAILY_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT USAGE_DATE, SERVICE_TYPE, CREDITS_USED_COMPUTE, CREDITS_USED_CLOUD_SERVICES, CREDITS_USED, "
                     f"CREDITS_ADJUSTMENT_CLOUD_SERVICES, CREDITS_BILLED FROM {AU}.METERING_DAILY_HISTORY "
                     f"WHERE USAGE_DATE >= TO_DATE({WINDOW}) AND USAGE_DATE < TO_DATE({WINDOW_END})"),
    HarvestQuery("QUERY_HISTORY", database_role="SNOWFLAKE.GOVERNANCE_VIEWER",
                 sql="SELECT q.QUERY_ID, q.QUERY_TEXT, q.QUERY_PARAMETERIZED_HASH, q.QUERY_TYPE, q.DATABASE_NAME, "
                     "q.SCHEMA_NAME, q.USER_NAME, q.ROLE_NAME, q.WAREHOUSE_NAME, UPPER(REPLACE(q.WAREHOUSE_SIZE, '-', '')) AS WAREHOUSE_SIZE, "
                     "q.QUERY_TAG, q.EXECUTION_STATUS, q.ERROR_MESSAGE, q.START_TIME, q.END_TIME, q.TOTAL_ELAPSED_TIME, "
                     "q.EXECUTION_TIME, q.QUEUED_OVERLOAD_TIME, q.COMPILATION_TIME, q.BYTES_SCANNED, "
                     "q.PERCENTAGE_SCANNED_FROM_CACHE, q.BYTES_WRITTEN, q.ROWS_PRODUCED, q.ROWS_INSERTED, "
                     "q.PARTITIONS_SCANNED, q.PARTITIONS_TOTAL, q.BYTES_SPILLED_TO_LOCAL_STORAGE, "
                     "q.BYTES_SPILLED_TO_REMOTE_STORAGE, q.CREDITS_USED_CLOUD_SERVICES, s.CLIENT_APPLICATION_ID "
                     f"FROM {AU}.QUERY_HISTORY q LEFT JOIN {AU}.SESSIONS s ON s.SESSION_ID = q.SESSION_ID "
                     f"WHERE q.START_TIME >= {WINDOW} AND q.START_TIME < {WINDOW_END}"),
    HarvestQuery("QUERY_ATTRIBUTION_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT QUERY_ID, WAREHOUSE_NAME, QUERY_PARAMETERIZED_HASH, QUERY_TAG, USER_NAME, START_TIME, END_TIME, "
                     f"CREDITS_ATTRIBUTED_COMPUTE FROM {AU}.QUERY_ATTRIBUTION_HISTORY "
                     f"WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("ACCESS_HISTORY", database_role="SNOWFLAKE.GOVERNANCE_VIEWER",
                 sql="SELECT a.QUERY_ID, a.QUERY_START_TIME, a.USER_NAME, f.value:\"objectName\"::STRING AS OBJECT_NAME, "
                     "f.value:\"objectDomain\"::STRING AS OBJECT_DOMAIN, 'READ' AS ACCESS_TYPE "
                     f"FROM {AU}.ACCESS_HISTORY a, LATERAL FLATTEN(INPUT => a.BASE_OBJECTS_ACCESSED) f "
                     f"WHERE a.QUERY_START_TIME >= {WINDOW} AND a.QUERY_START_TIME < {WINDOW_END} "
                     "UNION ALL "
                     "SELECT a.QUERY_ID, a.QUERY_START_TIME, a.USER_NAME, f.value:\"objectName\"::STRING AS OBJECT_NAME, "
                     "f.value:\"objectDomain\"::STRING AS OBJECT_DOMAIN, 'WRITE' AS ACCESS_TYPE "
                     f"FROM {AU}.ACCESS_HISTORY a, LATERAL FLATTEN(INPUT => a.OBJECTS_MODIFIED) f "
                     f"WHERE a.QUERY_START_TIME >= {WINDOW} AND a.QUERY_START_TIME < {WINDOW_END}"),
    HarvestQuery("AUTOMATIC_CLUSTERING_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql=f"SELECT START_TIME, END_TIME, {_fq('DATABASE_NAME', 'SCHEMA_NAME', 'TABLE_NAME')} AS TABLE_NAME, "
                     "CREDITS_USED, NUM_BYTES_RECLUSTERED, NUM_ROWS_RECLUSTERED "
                     f"FROM {AU}.AUTOMATIC_CLUSTERING_HISTORY WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("SEARCH_OPTIMIZATION_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql=f"SELECT START_TIME, END_TIME, {_fq('DATABASE_NAME', 'SCHEMA_NAME', 'TABLE_NAME')} AS TABLE_NAME, "
                     f"CREDITS_USED FROM {AU}.SEARCH_OPTIMIZATION_HISTORY "
                     f"WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("MATERIALIZED_VIEW_REFRESH_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql=f"SELECT START_TIME, END_TIME, {_fq('DATABASE_NAME', 'SCHEMA_NAME', 'TABLE_NAME')} AS TABLE_NAME, "
                     f"CREDITS_USED FROM {AU}.MATERIALIZED_VIEW_REFRESH_HISTORY "
                     f"WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("STORAGE_USAGE", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT USAGE_DATE, STORAGE_BYTES, STAGE_BYTES, FAILSAFE_BYTES, HYBRID_TABLE_STORAGE_BYTES "
                     f"FROM {AU}.STORAGE_USAGE WHERE USAGE_DATE >= TO_DATE({WINDOW}) AND USAGE_DATE < TO_DATE({WINDOW_END})"),
    HarvestQuery("TABLES", database_role="SNOWFLAKE.OBJECT_VIEWER",
                 sql="SELECT t.TABLE_ID, t.TABLE_CATALOG, t.TABLE_SCHEMA, t.TABLE_NAME, "
                     f"{_fq('t.TABLE_CATALOG', 't.TABLE_SCHEMA', 't.TABLE_NAME')} AS FQ_NAME, t.TABLE_TYPE, "
                     "t.IS_TRANSIENT = 'YES' AS IS_TRANSIENT, t.IS_ICEBERG = 'YES' AS IS_ICEBERG, t.CLUSTERING_KEY, "
                     "t.ROW_COUNT, t.BYTES, t.RETENTION_TIME, t.CREATED, t.LAST_ALTERED, t.LAST_DDL, t.TABLE_OWNER, "
                     "t.COMMENT, m.CLONE_GROUP_ID, c.COLUMN_SIGNATURE "
                     f"FROM {AU}.TABLES t "
                     f"LEFT JOIN {AU}.TABLE_STORAGE_METRICS m ON m.ID = t.TABLE_ID "
                     "LEFT JOIN (SELECT TABLE_ID, SUBSTR(MD5(LISTAGG(COLUMN_NAME, ',') WITHIN GROUP (ORDER BY ORDINAL_POSITION)), 1, 16) "
                     f"AS COLUMN_SIGNATURE FROM {AU}.COLUMNS WHERE DELETED IS NULL GROUP BY TABLE_ID) c ON c.TABLE_ID = t.TABLE_ID "
                     "WHERE t.DELETED IS NULL"),
    HarvestQuery("TABLE_STORAGE_METRICS", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT ID, TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, "
                     f"{_fq('TABLE_CATALOG', 'TABLE_SCHEMA', 'TABLE_NAME')} AS FQ_NAME, IS_TRANSIENT = 'YES' AS IS_TRANSIENT, "
                     "ACTIVE_BYTES, TIME_TRAVEL_BYTES, FAILSAFE_BYTES, RETAINED_FOR_CLONE_BYTES, DELETED, CLONE_GROUP_ID "
                     f"FROM {AU}.TABLE_STORAGE_METRICS WHERE DELETED = FALSE"),
    HarvestQuery("COLUMNS", database_role="SNOWFLAKE.OBJECT_VIEWER",
                 sql="SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, "
                     f"{_fq('TABLE_CATALOG', 'TABLE_SCHEMA', 'TABLE_NAME')} AS FQ_NAME, COLUMN_NAME, ORDINAL_POSITION, "
                     f"DATA_TYPE, IS_NULLABLE, COMMENT FROM {AU}.COLUMNS WHERE DELETED IS NULL"),
    HarvestQuery("VIEWS", database_role="SNOWFLAKE.OBJECT_VIEWER",
                 sql="SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, "
                     f"{_fq('TABLE_CATALOG', 'TABLE_SCHEMA', 'TABLE_NAME')} AS FQ_NAME, VIEW_DEFINITION, "
                     f"IS_SECURE = 'YES' AS IS_SECURE, COMMENT FROM {AU}.VIEWS WHERE DELETED IS NULL"),
    HarvestQuery("OBJECT_DEPENDENCIES", database_role="SNOWFLAKE.OBJECT_VIEWER",
                 sql=f"SELECT {_fq('REFERENCING_DATABASE', 'REFERENCING_SCHEMA', 'REFERENCING_OBJECT_NAME')} AS REFERENCING_OBJECT_NAME, "
                     f"REFERENCING_OBJECT_DOMAIN, {_fq('REFERENCED_DATABASE', 'REFERENCED_SCHEMA', 'REFERENCED_OBJECT_NAME')} "
                     "AS REFERENCED_OBJECT_NAME, REFERENCED_OBJECT_DOMAIN, DEPENDENCY_TYPE "
                     f"FROM {AU}.OBJECT_DEPENDENCIES"),
    HarvestQuery("TASKS", database_role="MONITOR EXECUTION", pre="SHOW TASKS IN ACCOUNT",
                 sql="SELECT \"name\" AS TASK_NAME, \"database_name\" AS DATABASE_NAME, \"schema_name\" AS SCHEMA_NAME, "
                     f"{_fq(chr(34) + 'database_name' + chr(34), chr(34) + 'schema_name' + chr(34), chr(34) + 'name' + chr(34))} AS FQ_NAME, "
                     "\"owner\" AS OWNER, \"warehouse\" AS WAREHOUSE, \"schedule\" AS SCHEDULE, "
                     "NULLIF(ARRAY_TO_STRING(TRY_PARSE_JSON(\"predecessors\"), ','), '') AS PREDECESSORS, \"state\" AS STATE, "
                     "NULL AS TARGET_TABLE, \"definition\" AS DEFINITION FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("TASK_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql=f"SELECT NAME, DATABASE_NAME, SCHEMA_NAME, {_fq('DATABASE_NAME', 'SCHEMA_NAME', 'NAME')} AS FQ_NAME, STATE, "
                     "ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME, QUERY_START_TIME, COMPLETED_TIME, ROOT_TASK_ID, RUN_ID, "
                     f"ATTEMPT_NUMBER, QUERY_ID FROM {AU}.TASK_HISTORY "
                     f"WHERE SCHEDULED_TIME >= {WINDOW} AND SCHEDULED_TIME < {WINDOW_END}"),
    HarvestQuery("COPY_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql=f"SELECT FILE_NAME, {_fq('TABLE_CATALOG_NAME', 'TABLE_SCHEMA_NAME', 'TABLE_NAME')} AS TABLE_NAME, "
                     f"{_fq('PIPE_CATALOG_NAME', 'PIPE_SCHEMA_NAME', 'PIPE_NAME')} AS PIPE_NAME, LAST_LOAD_TIME, ROW_COUNT, "
                     f"ERROR_COUNT, STATUS FROM {AU}.COPY_HISTORY "
                     f"WHERE LAST_LOAD_TIME >= {WINDOW} AND LAST_LOAD_TIME < {WINDOW_END}"),
    HarvestQuery("PIPE_USAGE_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT START_TIME, END_TIME, PIPE_NAME, CREDITS_USED, BYTES_INSERTED, FILES_INSERTED "
                     f"FROM {AU}.PIPE_USAGE_HISTORY WHERE START_TIME >= {WINDOW} AND START_TIME < {WINDOW_END}"),
    HarvestQuery("REPLICATION_GROUPS", database_role="MONITOR USAGE", pre="SHOW REPLICATION GROUPS",
                 sql="SELECT \"name\" AS NAME, \"type\" AS TYPE, \"object_types\" AS OBJECT_TYPES, "
                     "NULL AS ALLOWED_DATABASES, \"replication_schedule\" AS REPLICATION_SCHEDULE, "
                     "\"is_primary\" = 'true' AS IS_PRIMARY FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("USERS", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql="SELECT u.NAME, u.TYPE, u.LOGIN_NAME, u.DEFAULT_ROLE, u.HAS_PASSWORD, u.HAS_MFA, u.HAS_RSA_PUBLIC_KEY, "
                     "u.EXT_AUTHN_UID, u.DISABLED, u.CREATED_ON, u.LAST_SUCCESS_LOGIN, p.POLICY_NAME AS NETWORK_POLICY, "
                     f"u.OWNER, u.COMMENT FROM {AU}.USERS u LEFT JOIN {AU}.POLICY_REFERENCES p "
                     "ON p.REF_ENTITY_DOMAIN = 'USER' AND p.REF_ENTITY_NAME = u.NAME AND p.POLICY_KIND = 'NETWORK_POLICY' "
                     "WHERE u.DELETED_ON IS NULL"),
    HarvestQuery("ROLES", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql=f"SELECT NAME, ROLE_TYPE, OWNER, COMMENT, CREATED_ON FROM {AU}.ROLES WHERE DELETED_ON IS NULL"),
    HarvestQuery("GRANTS_TO_ROLES", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql="SELECT PRIVILEGE, GRANTED_ON, NAME, TABLE_CATALOG, TABLE_SCHEMA, GRANTED_TO, GRANTEE_NAME, GRANT_OPTION, "
                     f"GRANTED_BY, CREATED_ON FROM {AU}.GRANTS_TO_ROLES WHERE DELETED_ON IS NULL"),
    HarvestQuery("GRANTS_TO_USERS", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql=f"SELECT ROLE, GRANTED_TO, GRANTEE_NAME, GRANTED_BY, CREATED_ON FROM {AU}.GRANTS_TO_USERS "
                     "WHERE DELETED_ON IS NULL"),
    HarvestQuery("LOGIN_HISTORY", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql="SELECT EVENT_ID, EVENT_TIMESTAMP, USER_NAME, CLIENT_IP, REPORTED_CLIENT_TYPE, FIRST_AUTHENTICATION_FACTOR, "
                     f"SECOND_AUTHENTICATION_FACTOR, IS_SUCCESS, ERROR_CODE, ERROR_MESSAGE FROM {AU}.LOGIN_HISTORY "
                     f"WHERE EVENT_TIMESTAMP >= {WINDOW} AND EVENT_TIMESTAMP < {WINDOW_END}"),
    HarvestQuery("NETWORK_POLICIES", database_role="SNOWFLAKE.SECURITY_VIEWER",
                 sql="SELECT NAME, ALLOWED_IP_LIST, BLOCKED_IP_LIST, ALLOWED_NETWORK_RULE_LIST, OWNER "
                     f"FROM {AU}.NETWORK_POLICIES WHERE DELETED IS NULL"),
    HarvestQuery("TAG_REFERENCES", database_role="SNOWFLAKE.GOVERNANCE_VIEWER",
                 sql="SELECT TAG_DATABASE, TAG_SCHEMA, TAG_NAME, TAG_VALUE, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_NAME, "
                     f"COLUMN_NAME, DOMAIN FROM {AU}.TAG_REFERENCES WHERE OBJECT_DELETED IS NULL"),
    HarvestQuery("POLICY_REFERENCES", database_role="SNOWFLAKE.GOVERNANCE_VIEWER",
                 sql="SELECT POLICY_NAME, POLICY_KIND, REF_DATABASE_NAME, REF_SCHEMA_NAME, REF_ENTITY_NAME, REF_ENTITY_DOMAIN, "
                     f"REF_COLUMN_NAME, TAG_NAME, POLICY_STATUS FROM {AU}.POLICY_REFERENCES"),
    HarvestQuery("DATA_METRIC_FUNCTION_REFERENCES", database_role="SNOWFLAKE.GOVERNANCE_VIEWER",
                 sql="SELECT METRIC_DATABASE_NAME, METRIC_NAME, "
                     f"{_fq('REF_DATABASE_NAME', 'REF_SCHEMA_NAME', 'REF_ENTITY_NAME')} AS REF_ENTITY_NAME, "
                     f"REF_ENTITY_DOMAIN, SCHEDULE, SCHEDULE_STATUS FROM {AU}.DATA_METRIC_FUNCTION_REFERENCES"),
    HarvestQuery("DATA_QUALITY_MONITORING_RESULTS", database_role="SNOWFLAKE.DATA_QUALITY_MONITORING_VIEWER (optional)",
                 sql=f"SELECT MEASUREMENT_TIME, {_fq('TABLE_DATABASE', 'TABLE_SCHEMA', 'TABLE_NAME')} AS TABLE_NAME, "
                     "METRIC_NAME, VALUE, NULL AS EXPECTATION_VIOLATED FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS "
                     f"WHERE MEASUREMENT_TIME >= {WINDOW} AND MEASUREMENT_TIME < {WINDOW_END}"),
    HarvestQuery("ALERTS", database_role="MONITOR EXECUTION", pre="SHOW ALERTS IN ACCOUNT",
                 sql="SELECT \"name\" AS NAME, \"database_name\" AS DATABASE_NAME, \"schema_name\" AS SCHEMA_NAME, "
                     "\"state\" AS STATE, \"condition\" AS CONDITION, \"action\" AS ACTION, "
                     "CASE WHEN \"condition\" ILIKE '%METERING%' OR \"condition\" ILIKE '%CREDITS%' THEN 'credit_anomaly' "
                     "WHEN \"condition\" ILIKE '%TASK_HISTORY%' THEN 'task_failure' "
                     "WHEN \"condition\" ILIKE '%LOGIN_HISTORY%' THEN 'login_anomaly' ELSE 'other' END AS ALERT_CLASS "
                     "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("BUDGETS", database_role="SNOWFLAKE.USAGE_VIEWER", pre="SHOW SNOWFLAKE.CORE.BUDGET IN ACCOUNT",
                 sql="SELECT \"name\" AS NAME, CASE WHEN \"name\" ILIKE '%CORTEX%' OR \"name\" ILIKE '%AI%' THEN 'CORTEX' "
                     "ELSE 'CUSTOM' END AS SCOPE, NULL AS SPENDING_LIMIT, NULL AS OBJECTS "
                     "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("CORTEX_USAGE_HISTORY", database_role="SNOWFLAKE.USAGE_VIEWER",
                 sql="SELECT q.START_TIME, q.END_TIME, c.FUNCTION_NAME, c.MODEL_NAME, NULL AS AGENT_NAME, q.ROLE_NAME, "
                     f"q.USER_NAME, c.TOKENS, c.TOKEN_CREDITS FROM {AU}.CORTEX_FUNCTIONS_QUERY_USAGE_HISTORY c "
                     f"JOIN {AU}.QUERY_HISTORY q ON q.QUERY_ID = c.QUERY_ID "
                     f"WHERE q.START_TIME >= {WINDOW} AND q.START_TIME < {WINDOW_END}"),
    HarvestQuery("SEMANTIC_VIEWS", database_role="SNOWFLAKE.OBJECT_VIEWER", pre="SHOW SEMANTIC VIEWS IN ACCOUNT",
                 sql="SELECT \"name\" AS NAME, \"database_name\" AS DATABASE_NAME, \"schema_name\" AS SCHEMA_NAME, "
                     "LOWER(REGEXP_REPLACE(\"name\", '^SV_', '')) AS KPI_DOMAIN, \"comment\" AS COMMENT "
                     "FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
    HarvestQuery("CORTEX_SEARCH_SERVICES", database_role="SNOWFLAKE.OBJECT_VIEWER", pre="SHOW CORTEX SEARCH SERVICES IN ACCOUNT",
                 sql="SELECT \"name\" AS NAME, \"database_name\" AS DATABASE_NAME, \"schema_name\" AS SCHEMA_NAME, "
                     "\"source\" AS SOURCE_TABLE, \"target_lag\" AS TARGET_LAG FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))"),
]}


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, sort_keys=True)
    return v


class LiveHarvester:
    """Harvest a Snowflake account through a DB-API connection into a sealed diagnostic snapshot."""

    def __init__(self, connection: Any, *, window_days: int, end: date | None = None,
                 client_inputs: Mapping[str, Any] | None = None,
                 bi_reports: Iterable[Mapping[str, Any]] = (), bi_measures: Iterable[Mapping[str, Any]] = (),
                 edition: str | None = None):
        self.connection = connection
        self.end = end or datetime.now(timezone.utc).date()
        self.start = self.end - timedelta(days=int(window_days) - 1)
        self.client_inputs = dict(client_inputs or {})
        self.bi_reports = [dict(r) for r in bi_reports]
        self.bi_measures = [dict(r) for r in bi_measures]
        self.edition = edition or self.client_inputs.get("edition")
        self.executed: list[str] = []

    @property
    def params(self) -> dict[str, Any]:
        return {"window_start": datetime.combine(self.start, time.min),
                "window_end": datetime.combine(self.end + timedelta(days=1), time.min),
                "edition": self.edition}

    def execute(self, cursor: Any, sql: str) -> list[dict]:
        assert_read_only(sql)                       # refused before anything reaches the connection
        used = {k: v for k, v in self.params.items() if f"%({k})s" in sql}
        cursor.execute(sql, used) if used else cursor.execute(sql)
        self.executed.append(sql)
        if cursor.description is None:
            return []
        cols = [str(d[0]).upper() for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def harvest_table(self, table: str) -> tuple[list[dict], str]:
        if table == "CLIENT_INPUTS":
            return [{"KEY": k, "VALUE": json.dumps(v, sort_keys=True)} for k, v in sorted(self.client_inputs.items())], "ok"
        if table == "BI_REPORTS":
            return self.bi_reports, "ok" if self.bi_reports else "not_supplied"
        if table == "BI_MEASURES":
            return self.bi_measures, "ok" if self.bi_measures else "not_supplied"
        q = HARVEST_QUERIES[table]
        cursor = self.connection.cursor()
        try:
            rows: list[dict] = []
            for sql in q.statements():
                rows = self.execute(cursor, sql)
            return rows, "ok"
        except Exception as e:  # noqa: BLE001 - a source the role cannot read is recorded, not fatal
            from altitude.core.errors import ReadOnlyViolation

            if isinstance(e, ReadOnlyViolation):
                raise
            return [], "unavailable"
        finally:
            close = getattr(cursor, "close", None)
            if close:
                close()

    def harvest(self, directory: str | Path, snapshot_id: str | None = None, metadata: Mapping[str, Any] | None = None,
                sealed_at: datetime | None = None) -> Snapshot:
        tables: dict[str, list[dict]] = {}
        status: dict[str, str] = {}
        for table in HARVEST_SCHEMA:
            rows, st = self.harvest_table(table)
            columns = HARVEST_SCHEMA[table]["columns"]
            tables[table] = [{c: _cell(r.get(c)) for c in columns} for r in rows]
            status[table] = st
        account = (tables["ACCOUNT_INFO"][0].get("ACCOUNT_NAME") if tables["ACCOUNT_INFO"] else None) or "ACCOUNT"
        snapshot_id = snapshot_id or f"SNAP-{account}-{self.end.isoformat()}-LIVE"
        meta = {"account_name": account, "window_start": self.start.isoformat(), "window_end": self.end.isoformat(),
                "source": "live", "harvest_status": status, **(metadata or {})}
        writer = SnapshotWriter(directory, snapshot_id, kind="diagnostic", metadata=meta)
        for table, info in HARVEST_SCHEMA.items():
            writer.add_table_from_rows(table, tables[table], info["columns"])
        return writer.seal(sealed_at=sealed_at)


def connect_snowflake(**kwargs: Any) -> Any:  # pragma: no cover - requires the optional extra
    """Open a key-pair authenticated connection with the optional ``snowflake-connector-python`` extra."""
    try:
        import snowflake.connector  # type: ignore
    except ModuleNotFoundError as e:
        raise RuntimeError("install the optional extra: pip install 'altitude[snowflake]'") from e
    return snowflake.connector.connect(**kwargs)
