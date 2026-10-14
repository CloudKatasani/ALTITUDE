"""Read-only agent tools over telemetry (Section 18.3).

Each tool is a named, read-only function with a declared table footprint. An agent may only call the
tools listed in its catalogue ``tool_scope``; every call is recorded (arguments, tables read, row count
and a content hash of the result) and lands in the immutable ``agent_tool_call`` log. In a client
account the same tools are deployed as stored procedures/UDFs over ACCOUNT_USAGE and the Package O
observability database (see ``generated/agents``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from altitude.core.ids import content_hash
from altitude.core.rubric import RubricSet

from .errors import ToolScopeViolation
from .telemetry import Telemetry, assert_read_only


@dataclass(frozen=True)
class Tool:
    name: str
    tables: tuple[str, ...]
    description: str
    fn: Callable[..., list[dict]]


TOOLS: dict[str, Tool] = {}


def tool(name: str, tables: tuple[str, ...], description: str):
    def deco(fn: Callable[..., list[dict]]) -> Callable[..., list[dict]]:
        TOOLS[name] = Tool(name, tables, description, fn)
        return fn
    return deco


def _since(tel: Telemetry, days: float) -> datetime:
    return tel.as_of - timedelta(days=days)


# --------------------------------------------------------------------------- cost
@tool("daily_credits", ("METERING_DAILY_HISTORY",), "Billed credits per day (all services).")
def daily_credits(tel: Telemetry, days: int) -> list[dict]:
    return tel.query(
        "SELECT USAGE_DATE AS DAY, SUM(CREDITS_BILLED) AS CREDITS FROM METERING_DAILY_HISTORY "
        "WHERE USAGE_DATE > CAST(? AS DATE) - CAST(? AS INTEGER) AND USAGE_DATE <= CAST(? AS DATE) "
        "GROUP BY 1 ORDER BY 1", [tel.as_of, int(days), tel.as_of])


@tool("warehouse_daily_credits", ("WAREHOUSE_METERING_HISTORY",), "Credits per warehouse per day.")
def warehouse_daily_credits(tel: Telemetry, days: int) -> list[dict]:
    return tel.query(
        "SELECT WAREHOUSE_NAME, CAST(START_TIME AS DATE) AS DAY, SUM(CREDITS_USED) AS CREDITS "
        "FROM WAREHOUSE_METERING_HISTORY WHERE START_TIME >= ? AND START_TIME <= ? GROUP BY 1, 2 ORDER BY 1, 2",
        [_since(tel, days), tel.as_of])


@tool("signature_credits", ("QUERY_ATTRIBUTION_HISTORY",),
      "Attributed compute credits per query signature, user and day for one warehouse up to a day.")
def signature_credits(tel: Telemetry, warehouse: str, day: str, baseline_days: int) -> list[dict]:
    return tel.query(
        "SELECT QUERY_PARAMETERIZED_HASH AS SIG, USER_NAME, CAST(START_TIME AS DATE) AS DAY, "
        "SUM(CREDITS_ATTRIBUTED_COMPUTE) AS CREDITS FROM QUERY_ATTRIBUTION_HISTORY "
        "WHERE WAREHOUSE_NAME = ? AND CAST(START_TIME AS DATE) <= CAST(? AS DATE) "
        "AND CAST(START_TIME AS DATE) >= CAST(? AS DATE) - CAST(? AS INTEGER) GROUP BY 1, 2, 3 ORDER BY 3, 1, 2",
        [warehouse, day, day, int(baseline_days)])


# --------------------------------------------------------------------------- warehouses
@tool("warehouse_config", ("WAREHOUSES",), "Current warehouse settings.")
def warehouse_config(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM WAREHOUSES ORDER BY WAREHOUSE_NAME")


@tool("warehouse_utilisation", ("WAREHOUSE_METERING_HISTORY", "QUERY_ATTRIBUTION_HISTORY"),
      "Billed compute vs compute attributed to queries per warehouse (idle share).")
def warehouse_utilisation(tel: Telemetry, days: int) -> list[dict]:
    return tel.query(
        """
        WITH b AS (SELECT WAREHOUSE_NAME, SUM(CREDITS_USED_COMPUTE) AS BILLED FROM WAREHOUSE_METERING_HISTORY
                   WHERE START_TIME >= ? AND START_TIME <= ? GROUP BY 1),
             a AS (SELECT WAREHOUSE_NAME, SUM(CREDITS_ATTRIBUTED_COMPUTE) AS ATTRIBUTED FROM QUERY_ATTRIBUTION_HISTORY
                   WHERE START_TIME >= ? AND START_TIME <= ? GROUP BY 1)
        SELECT b.WAREHOUSE_NAME, b.BILLED, coalesce(a.ATTRIBUTED, 0) AS ATTRIBUTED,
               CASE WHEN b.BILLED > 0 THEN greatest(0, 1 - coalesce(a.ATTRIBUTED, 0) / b.BILLED) ELSE 0 END AS IDLE_RATIO
        FROM b LEFT JOIN a USING (WAREHOUSE_NAME) ORDER BY 1
        """, [_since(tel, days), tel.as_of, _since(tel, days), tel.as_of])


@tool("warehouse_load", ("WAREHOUSE_LOAD_HISTORY",), "Average and peak-hour queued load per warehouse.")
def warehouse_load(tel: Telemetry, hours: float, warehouse: str | None = None) -> list[dict]:
    return tel.query(
        """
        WITH h AS (SELECT WAREHOUSE_NAME, hour(START_TIME) AS HOD,
                          AVG(AVG_QUEUED_LOAD + AVG_QUEUED_PROVISIONING) AS Q, AVG(AVG_RUNNING) AS R
                   FROM WAREHOUSE_LOAD_HISTORY WHERE START_TIME >= ? AND START_TIME <= ?
                     AND (? IS NULL OR WAREHOUSE_NAME = ?) GROUP BY 1, 2)
        SELECT WAREHOUSE_NAME, AVG(Q) AS AVG_QUEUED, MAX(Q) AS PEAK_HOUR_QUEUED, AVG(R) AS AVG_RUNNING
        FROM h GROUP BY 1 ORDER BY 1
        """, [tel.as_of - timedelta(hours=hours), tel.as_of, warehouse, warehouse])


@tool("warehouse_query_profile", ("QUERY_HISTORY",), "Execution-time percentiles and spilling per warehouse.")
def warehouse_query_profile(tel: Telemetry, days: int) -> list[dict]:
    return tel.query(
        "SELECT WAREHOUSE_NAME, COUNT(*) AS QUERIES, quantile_cont(EXECUTION_TIME, 0.9) AS P90_EXEC_MS, "
        "SUM(BYTES_SPILLED_TO_LOCAL_STORAGE) AS SPILL_LOCAL, SUM(BYTES_SPILLED_TO_REMOTE_STORAGE) AS SPILL_REMOTE "
        "FROM QUERY_HISTORY WHERE WAREHOUSE_NAME IS NOT NULL AND START_TIME >= ? AND START_TIME <= ? "
        "GROUP BY 1 ORDER BY 1", [_since(tel, days), tel.as_of])


# --------------------------------------------------------------------------- pipelines
@tool("task_failures", ("TASK_HISTORY",), "Failed task runs in the lookback window, with the task's latest state.")
def task_failures(tel: Telemetry, days: float) -> list[dict]:
    return tel.query(
        """
        WITH latest AS (SELECT FQ_NAME, arg_max(STATE, SCHEDULED_TIME) AS LATEST_STATE FROM TASK_HISTORY GROUP BY 1)
        SELECT t.FQ_NAME, t.STATE, t.ERROR_CODE, t.ERROR_MESSAGE, t.SCHEDULED_TIME, t.QUERY_START_TIME,
               t.COMPLETED_TIME, t.RUN_ID, t.ROOT_TASK_ID, t.ATTEMPT_NUMBER, l.LATEST_STATE
        FROM TASK_HISTORY t JOIN latest l USING (FQ_NAME)
        WHERE t.STATE = 'FAILED' AND t.SCHEDULED_TIME >= ? AND t.SCHEDULED_TIME <= ?
        ORDER BY t.SCHEDULED_TIME, t.FQ_NAME
        """, [_since(tel, days), tel.as_of])


@tool("task_definitions", ("TASKS",), "Task inventory: schedule, predecessors, target table.")
def task_definitions(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM TASKS ORDER BY FQ_NAME")


@tool("task_idempotency", ("TAG_REFERENCES",), "Tasks tagged IDEMPOTENT = 'true' in the account.")
def task_idempotency(tel: Telemetry) -> list[dict]:
    return tel.query(
        "SELECT OBJECT_DATABASE || '.' || OBJECT_SCHEMA || '.' || OBJECT_NAME AS FQ_NAME, TAG_VALUE "
        "FROM TAG_REFERENCES WHERE DOMAIN = 'TASK' AND upper(TAG_NAME) = 'IDEMPOTENT' ORDER BY 1")


@tool("recent_ddl", ("QUERY_HISTORY",), "DDL statements touching the given objects within a window.")
def recent_ddl(tel: Telemetry, objects: list[str], before: datetime, hours: float) -> list[dict]:
    if not objects:
        return []
    return tel.query(
        """
        SELECT QUERY_ID, QUERY_TYPE, QUERY_TEXT, USER_NAME, ROLE_NAME, QUERY_TAG, START_TIME
        FROM QUERY_HISTORY
        WHERE (QUERY_TYPE LIKE 'ALTER%' OR QUERY_TYPE LIKE 'CREATE%' OR QUERY_TYPE LIKE 'DROP%' OR QUERY_TYPE = 'RENAME_TABLE')
          AND START_TIME <= ? AND START_TIME >= ?
          AND list_has_any(regexp_extract_all(upper(QUERY_TEXT), '[A-Z0-9_$]+\\.[A-Z0-9_$]+\\.[A-Z0-9_$]+'), ?)
        ORDER BY START_TIME, QUERY_ID
        """, [before, before - timedelta(hours=hours), [o.upper() for o in objects]])


@tool("load_errors", ("COPY_HISTORY",), "Files loaded with errors or not loaded in the window.")
def load_errors(tel: Telemetry, days: float) -> list[dict]:
    return tel.query(
        "SELECT TABLE_NAME, FILE_NAME, PIPE_NAME, LAST_LOAD_TIME, ROW_COUNT, ERROR_COUNT, STATUS FROM COPY_HISTORY "
        "WHERE (ERROR_COUNT > 0 OR STATUS <> 'Loaded') AND LAST_LOAD_TIME >= ? AND LAST_LOAD_TIME <= ? "
        "ORDER BY LAST_LOAD_TIME, FILE_NAME", [_since(tel, days), tel.as_of])


# --------------------------------------------------------------------------- access
@tool("users", ("USERS",), "User inventory with authentication posture and last login.")
def users(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM USERS ORDER BY NAME")


@tool("user_role_grants", ("GRANTS_TO_USERS",), "Role grants to users.")
def user_role_grants(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM GRANTS_TO_USERS ORDER BY GRANTEE_NAME, ROLE")


@tool("role_grants", ("GRANTS_TO_ROLES",), "Privilege and role grants to roles.")
def role_grants(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM GRANTS_TO_ROLES ORDER BY GRANTEE_NAME, GRANTED_ON, NAME, PRIVILEGE")


@tool("roles", ("ROLES",), "Role inventory.")
def roles(tel: Telemetry) -> list[dict]:
    return tel.query("SELECT * FROM ROLES ORDER BY NAME")


@tool("privileged_usage", ("QUERY_HISTORY",), "Statements executed under a privileged role, per user.")
def privileged_usage(tel: Telemetry, role: str, days: int) -> list[dict]:
    return tel.query(
        "SELECT USER_NAME, COUNT(*) AS STATEMENTS, MAX(START_TIME) AS LAST_USED FROM QUERY_HISTORY "
        "WHERE ROLE_NAME = ? AND START_TIME >= ? AND START_TIME <= ? GROUP BY 1 ORDER BY 1",
        [role, _since(tel, days), tel.as_of])


# --------------------------------------------------------------------------- data quality
@tool("dq_violations", ("DATA_QUALITY_MONITORING_RESULTS",), "Data metric function expectation violations.")
def dq_violations(tel: Telemetry, days: float) -> list[dict]:
    return tel.query(
        "SELECT MEASUREMENT_TIME, TABLE_NAME, METRIC_NAME, VALUE FROM DATA_QUALITY_MONITORING_RESULTS "
        "WHERE EXPECTATION_VIOLATED AND MEASUREMENT_TIME >= ? AND MEASUREMENT_TIME <= ? "
        "ORDER BY MEASUREMENT_TIME, TABLE_NAME, METRIC_NAME", [_since(tel, days), tel.as_of])


@tool("table_lineage", ("ACCESS_HISTORY", "OBJECT_DEPENDENCIES", "TASKS"),
      "Upstream -> downstream edges from access history (read->write), object dependencies and task targets.")
def table_lineage(tel: Telemetry, days: float) -> list[dict]:
    return tel.query(
        """
        SELECT DISTINCT r.OBJECT_NAME AS UPSTREAM, w.OBJECT_NAME AS DOWNSTREAM, 'access_history' AS EVIDENCE
        FROM ACCESS_HISTORY r JOIN ACCESS_HISTORY w ON r.QUERY_ID = w.QUERY_ID
        WHERE r.ACCESS_TYPE = 'READ' AND w.ACCESS_TYPE = 'WRITE' AND r.OBJECT_NAME <> w.OBJECT_NAME
          AND r.QUERY_START_TIME >= ? AND r.QUERY_START_TIME <= ?
        UNION
        SELECT DISTINCT REFERENCED_OBJECT_NAME, REFERENCING_OBJECT_NAME, 'object_dependencies' FROM OBJECT_DEPENDENCIES
        UNION
        SELECT DISTINCT FQ_NAME, TARGET_TABLE, 'task_target' FROM TASKS WHERE TARGET_TABLE IS NOT NULL
        ORDER BY 1, 2, 3
        """, [_since(tel, days), tel.as_of])


@tool("table_owners", ("TAG_REFERENCES",), "DATA_OWNER tag per table.")
def table_owners(tel: Telemetry) -> list[dict]:
    return tel.query(
        "SELECT OBJECT_DATABASE || '.' || OBJECT_SCHEMA || '.' || OBJECT_NAME AS FQ_NAME, TAG_VALUE AS OWNER "
        "FROM TAG_REFERENCES WHERE TAG_NAME = 'DATA_OWNER' AND DOMAIN = 'TABLE' ORDER BY 1")


@tool("tier1_tables", ("TAG_REFERENCES", "CLIENT_INPUTS"), "Tier-1 tables (TIER tag or client input).")
def tier1_tables(tel: Telemetry) -> list[dict]:
    tagged = tel.query(
        "SELECT OBJECT_DATABASE || '.' || OBJECT_SCHEMA || '.' || OBJECT_NAME AS FQ_NAME FROM TAG_REFERENCES "
        "WHERE TAG_NAME = 'TIER' AND lower(TAG_VALUE) = 'tier1' AND DOMAIN = 'TABLE'")
    names = {r["FQ_NAME"] for r in tagged} | set(tel.client_input("tier1_tables", []) or [])
    return [{"FQ_NAME": n} for n in sorted(names)]


# --------------------------------------------------------------------------- release watch
@tool("usage_signature_scan", ("QUERY_HISTORY", "VIEWS", "USERS", "WAREHOUSES"),
      "Match a behaviour-change usage signature against query text, view definitions or object metadata.")
def usage_signature_scan(tel: Telemetry, kind: str, days: int, pattern: str | None = None,
                         sql: str | None = None) -> list[dict]:
    if kind == "query_text":
        return tel.query(
            "SELECT QUERY_PARAMETERIZED_HASH AS OBJECT_NAME, COUNT(*) AS MATCHES, "
            "COUNT(DISTINCT USER_NAME) AS USERS, min(QUERY_TEXT) AS DETAIL FROM QUERY_HISTORY "
            "WHERE START_TIME >= ? AND START_TIME <= ? AND regexp_matches(QUERY_TEXT, ?, 'i') "
            "GROUP BY 1 ORDER BY 1", [_since(tel, days), tel.as_of, pattern])
    if kind == "view_definition":
        return tel.query(
            "SELECT FQ_NAME AS OBJECT_NAME, 1 AS MATCHES, 0 AS USERS, VIEW_DEFINITION AS DETAIL FROM VIEWS "
            "WHERE regexp_matches(VIEW_DEFINITION, ?, 'i') ORDER BY 1", [pattern])
    if kind == "sql":
        assert sql is not None
        assert_read_only(sql)
        rows = tel.query(sql)
        return sorted(({"OBJECT_NAME": r["OBJECT_NAME"], "MATCHES": 1, "USERS": 0, "DETAIL": r.get("DETAIL")}
                       for r in rows), key=lambda r: str(r["OBJECT_NAME"]))
    raise ValueError(f"unknown signature kind {kind!r}")


# --------------------------------------------------------------------------- scoped context
@dataclass
class ToolCall:
    seq: int
    tool: str
    arguments: dict
    tables_read: list[str]
    rows_returned: int
    result_hash: str


@dataclass
class ToolContext:
    """The only door from an agent to telemetry: scope-checked, recorded, read-only."""

    agent_id: str
    scope: tuple[str, ...]
    telemetry: Telemetry
    rubrics: RubricSet
    calls: list[ToolCall] = field(default_factory=list)

    def call(self, name: str, **kwargs: Any) -> list[dict]:
        if name not in self.scope:
            raise ToolScopeViolation(f"{self.agent_id} called tool {name!r} outside its scope {list(self.scope)}")
        t = TOOLS[name]
        rows = t.fn(self.telemetry, **kwargs)
        self.calls.append(ToolCall(len(self.calls) + 1, name, {k: _jsonable(v) for k, v in sorted(kwargs.items())},
                                   list(t.tables), len(rows), content_hash(rows, 16)))
        return rows


def _jsonable(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v
