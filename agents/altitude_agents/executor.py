"""Executors: the only path from an approved/pre-approved agent action to a Snowflake account.

- :class:`SimulatedSnowflake` keeps a mutable copy of WAREHOUSES / USERS / GRANTS / ROLES / TASKS /
  TASK_HISTORY / TAG_REFERENCES in DuckDB, interprets the action-template vocabulary and records every
  executed statement. Used by tests, evals and demos.
- :class:`LiveExecutor` renders the same SQL against a DB-API connection (e.g.
  ``snowflake.connector.connect(...)`` under the agent's service identity); ``dry_run=True`` only records.

SQL is rendered from catalogue templates by :func:`render_sql`; every identifier and value is validated
against its declared type before it is interpolated, so templates cannot be used for injection.
"""

from __future__ import annotations

import re
import string
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, Protocol

import duckdb

from .errors import ActionRefused, UnsupportedStatement
from .telemetry import Telemetry

IDENT = r"[A-Za-z_][A-Za-z0-9_$]*(?:\.[A-Za-z_][A-Za-z0-9_$]*){0,2}"
_IDENT_RE = re.compile(rf"^{IDENT}$")
WAREHOUSE_SIZES = ("XSMALL", "SMALL", "MEDIUM", "LARGE", "XLARGE", "XXLARGE", "XXXLARGE", "X4LARGE", "X5LARGE",
                   "X6LARGE")
PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "USAGE", "MODIFY", "OPERATE",
              "MONITOR", "APPLY", "OWNERSHIP")
OBJECT_KINDS = ("TABLE", "VIEW", "SCHEMA", "DATABASE", "WAREHOUSE", "TASK", "STAGE", "FUNCTION", "PROCEDURE")
# Statements no agent may ever emit, whatever its catalogue says (Section 18.2 guardrails).
ALWAYS_FORBIDDEN = ("DELETE", "TRUNCATE", "DROP TABLE", "DROP DATABASE", "DROP SCHEMA", "INSERT OVERWRITE")


def validate_value(value: Any, kind: str, name: str) -> str:
    """Return the SQL rendering of ``value`` for a declared parameter ``kind`` or raise ActionRefused."""
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ActionRefused(f"parameter {name!r} must be an integer, got {value!r}")
        return str(value)
    if kind == "warehouse_size":
        v = str(value).upper().replace("-", "")
        if v not in WAREHOUSE_SIZES:
            raise ActionRefused(f"parameter {name!r}: unknown warehouse size {value!r}")
        return v
    if kind == "identifier":
        if not isinstance(value, str) or not _IDENT_RE.match(value):
            raise ActionRefused(f"parameter {name!r}: invalid identifier {value!r}")
        return value
    if kind == "privilege":
        if str(value).upper() not in PRIVILEGES:
            raise ActionRefused(f"parameter {name!r}: unknown privilege {value!r}")
        return str(value).upper()
    if kind == "object_kind":
        if str(value).upper() not in OBJECT_KINDS:
            raise ActionRefused(f"parameter {name!r}: unknown object kind {value!r}")
        return str(value).upper()
    if kind == "boolean":
        if not isinstance(value, bool):
            raise ActionRefused(f"parameter {name!r} must be a boolean, got {value!r}")
        return "TRUE" if value else "FALSE"
    if kind == "text":
        return "'" + str(value).replace("'", "''") + "'"
    raise ActionRefused(f"parameter {name!r}: unknown parameter kind {kind!r}")


# Kinds of the properties an executor reports via ``current()`` (used when rendering rollback SQL).
CAPTURE_KINDS = {"auto_suspend": "integer", "warehouse_size": "warehouse_size", "max_cluster_count": "integer",
                 "min_cluster_count": "integer", "disabled": "boolean", "auto_resume": "boolean"}


def render_sql(template: str, target: str, params: dict, kinds: dict, previous: dict | None = None) -> str:
    """Render a catalogue template with validated values (``{target}``, ``{<param>}``, ``{previous.<prop>}``)."""
    values: dict[str, Any] = {"target": validate_value(target, "identifier", "target")}
    for name, kind in kinds.items():
        if name in params:
            values[name] = validate_value(params[name], kind, name)
    prev = {}
    for k, v in (previous or {}).items():
        prev[k] = validate_value(v, CAPTURE_KINDS.get(k, "identifier"), f"previous.{k}") if v is not None else "NULL"
    values["previous"] = SimpleNamespace(**prev)
    fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
    missing = [f for f in fields if f.split(".")[0] not in values or
               (f.startswith("previous.") and f.split(".", 1)[1] not in prev)]
    if missing:
        raise ActionRefused(f"template {template!r} is missing values for {sorted(missing)}")
    return template.format(**values)


def forbidden_in(sql: str, forbidden: tuple[str, ...] | list[str]) -> str | None:
    """Return the first forbidden statement verb that begins any statement in ``sql``."""
    for stmt in sql.split(";"):
        norm = re.sub(r"\s+", " ", stmt.strip().upper())
        for f in (*ALWAYS_FORBIDDEN, *forbidden):
            f = f.upper()
            if norm == f or norm.startswith(f + " "):
                return f
    return None


class Executor(Protocol):
    executed: list[str]

    def run(self, sql: str) -> None: ...

    def current(self, object_type: str, name: str) -> dict: ...


# --------------------------------------------------------------------------- simulated account
_SIM_TABLES = ("WAREHOUSES", "USERS", "GRANTS_TO_USERS", "GRANTS_TO_ROLES", "ROLES", "TASKS", "TASK_HISTORY",
               "TAG_REFERENCES")


class SimulatedSnowflake:
    """A mutable, in-memory stand-in for the account's control surface (DuckDB)."""

    def __init__(self, telemetry: Telemetry, clock: Callable[[], datetime] | None = None):
        self.con = duckdb.connect(":memory:")
        self.executed: list[str] = []
        self.clock = clock or (lambda: datetime.now(timezone.utc).replace(tzinfo=None))
        for t in _SIM_TABLES:
            rows = telemetry.query(f'SELECT * FROM "{t}"')
            cols = telemetry.query(
                "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ? "
                "ORDER BY ordinal_position", [t])
            self.con.execute(f'CREATE TABLE "{t}" (' + ", ".join(f'"{c["column_name"]}" {c["data_type"]}'
                                                                   for c in cols) + ")")
            if rows:
                names = [c["column_name"] for c in cols]
                self.con.executemany(f'INSERT INTO "{t}" VALUES (' + ", ".join("?" for _ in names) + ")",
                                     [[r[n] for n in names] for r in rows])
        self.con.execute('ALTER TABLE USERS ADD COLUMN AUTHENTICATION_POLICY VARCHAR')

    # ------------------------------------------------------------------ inspection
    def rows(self, sql: str, params: list | None = None) -> list[dict]:
        cur = self.con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def warehouse(self, name: str) -> dict:
        rows = self.rows("SELECT * FROM WAREHOUSES WHERE upper(WAREHOUSE_NAME) = upper(?)", [name])
        if not rows:
            raise UnsupportedStatement(f"Warehouse '{name}' does not exist or not authorized.")
        return rows[0]

    def current(self, object_type: str, name: str) -> dict:
        if object_type == "warehouse":
            w = self.warehouse(name)
            return {"auto_suspend": w["AUTO_SUSPEND"], "warehouse_size": w["WAREHOUSE_SIZE"],
                    "max_cluster_count": w["MAX_CLUSTER_COUNT"], "min_cluster_count": w["MIN_CLUSTER_COUNT"],
                    "auto_resume": w["AUTO_RESUME"]}
        if object_type == "user":
            rows = self.rows("SELECT * FROM USERS WHERE upper(NAME) = upper(?)", [name])
            if not rows:
                raise UnsupportedStatement(f"User '{name}' does not exist or not authorized.")
            return {"disabled": bool(rows[0]["DISABLED"]), "authentication_policy": rows[0]["AUTHENTICATION_POLICY"]}
        return {}

    # ------------------------------------------------------------------ execution
    def run(self, sql: str) -> None:
        stmt = sql.strip().rstrip(";").strip()
        handled = (self._alter_warehouse(stmt) or self._alter_user(stmt) or self._role_grant(stmt)
                   or self._privilege_grant(stmt) or self._execute_task(stmt) or self._table_tag(stmt))
        if not handled:
            raise UnsupportedStatement(f"simulated account does not support: {stmt}")
        self.executed.append(stmt)

    _WH_PROPS = {"AUTO_SUSPEND": "int", "WAREHOUSE_SIZE": "size", "MAX_CLUSTER_COUNT": "int",
                 "MIN_CLUSTER_COUNT": "int", "AUTO_RESUME": "bool", "STATEMENT_TIMEOUT_IN_SECONDS": "int",
                 "RESOURCE_MONITOR": "ident"}

    def _alter_warehouse(self, stmt: str) -> bool:
        m = re.match(rf"^ALTER\s+WAREHOUSE\s+({IDENT})\s+SET\s+(.+)$", stmt, re.I | re.S)
        if not m:
            return False
        name = m.group(1)
        self.warehouse(name)
        for key, raw in re.findall(r"([A-Za-z_]+)\s*=\s*('[^']*'|[^\s,]+)", m.group(2)):
            key = key.upper()
            kind = self._WH_PROPS.get(key)
            if kind is None:
                raise UnsupportedStatement(f"unsupported warehouse property {key}")
            val: Any = raw.strip("'")
            if kind == "int":
                val = int(val)
            elif kind == "bool":
                val = val.upper() == "TRUE"
            elif kind == "size":
                val = validate_value(val, "warehouse_size", key)
            self.con.execute(f'UPDATE WAREHOUSES SET "{key}" = ? WHERE upper(WAREHOUSE_NAME) = upper(?)', [val, name])
        return True

    def _alter_user(self, stmt: str) -> bool:
        m = re.match(rf"^ALTER\s+USER\s+({IDENT})\s+SET\s+DISABLED\s*=\s*(TRUE|FALSE)$", stmt, re.I)
        if m:
            self.current("user", m.group(1))
            self.con.execute("UPDATE USERS SET DISABLED = ? WHERE upper(NAME) = upper(?)",
                             [m.group(2).upper() == "TRUE", m.group(1)])
            return True
        m = re.match(rf"^ALTER\s+USER\s+({IDENT})\s+SET\s+AUTHENTICATION\s+POLICY\s+({IDENT})$", stmt, re.I)
        if m:
            self.current("user", m.group(1))
            self.con.execute("UPDATE USERS SET AUTHENTICATION_POLICY = ? WHERE upper(NAME) = upper(?)",
                             [m.group(2), m.group(1)])
            return True
        m = re.match(rf"^ALTER\s+USER\s+({IDENT})\s+UNSET\s+AUTHENTICATION\s+POLICY$", stmt, re.I)
        if m:
            self.current("user", m.group(1))
            self.con.execute("UPDATE USERS SET AUTHENTICATION_POLICY = NULL WHERE upper(NAME) = upper(?)",
                             [m.group(1)])
            return True
        return False

    def _role_grant(self, stmt: str) -> bool:
        m = re.match(rf"^(GRANT|REVOKE)\s+ROLE\s+({IDENT})\s+(TO|FROM)\s+USER\s+({IDENT})$", stmt, re.I)
        if not m:
            return False
        verb, role, _, user = m.group(1).upper(), m.group(2).upper(), m.group(3), m.group(4).upper()
        if verb == "REVOKE":
            self.con.execute("DELETE FROM GRANTS_TO_USERS WHERE upper(ROLE) = ? AND upper(GRANTEE_NAME) = ?",
                             [role, user])
        else:
            exists = self.rows("SELECT 1 FROM GRANTS_TO_USERS WHERE upper(ROLE) = ? AND upper(GRANTEE_NAME) = ?",
                               [role, user])
            if not exists:
                self.con.execute("INSERT INTO GRANTS_TO_USERS (ROLE, GRANTED_TO, GRANTEE_NAME, GRANTED_BY, CREATED_ON) "
                                 "VALUES (?, 'USER', ?, 'SECURITYADMIN', ?)", [role, user, self.clock()])
        return True

    def _privilege_grant(self, stmt: str) -> bool:
        m = re.match(rf"^(GRANT|REVOKE)\s+([A-Z_]+)\s+ON\s+([A-Z_]+)\s+({IDENT})\s+(TO|FROM)\s+ROLE\s+({IDENT})$",
                     stmt, re.I)
        if not m:
            return False
        verb, priv, kind, obj, _, role = (m.group(1).upper(), m.group(2).upper(), m.group(3).upper(),
                                          m.group(4).upper(), m.group(5), m.group(6).upper())
        parts = obj.split(".")
        name = parts[-1]
        catalog = parts[0] if len(parts) == 3 else None
        schema = parts[1] if len(parts) == 3 else None
        where = ("upper(PRIVILEGE) = ? AND upper(GRANTED_ON) = ? AND upper(NAME) = ? AND upper(GRANTEE_NAME) = ? "
                 "AND coalesce(upper(TABLE_CATALOG), '') = coalesce(?, '') AND coalesce(upper(TABLE_SCHEMA), '') = coalesce(?, '')")
        args = [priv, kind, name, role, catalog, schema]
        if verb == "REVOKE":
            self.con.execute(f"DELETE FROM GRANTS_TO_ROLES WHERE {where}", args)
        elif not self.rows(f"SELECT 1 FROM GRANTS_TO_ROLES WHERE {where}", args):
            self.con.execute(
                "INSERT INTO GRANTS_TO_ROLES (PRIVILEGE, GRANTED_ON, NAME, TABLE_CATALOG, TABLE_SCHEMA, GRANTED_TO, "
                "GRANTEE_NAME, GRANT_OPTION, GRANTED_BY, CREATED_ON) VALUES (?, ?, ?, ?, ?, 'ROLE', ?, FALSE, 'SECURITYADMIN', ?)",
                [priv, kind, name, catalog, schema, role, self.clock()])
        return True

    def _execute_task(self, stmt: str) -> bool:
        m = re.match(rf"^EXECUTE\s+TASK\s+({IDENT})$", stmt, re.I)
        if not m:
            return False
        fq = m.group(1).upper()
        if not self.rows("SELECT 1 FROM TASKS WHERE upper(FQ_NAME) = ?", [fq]):
            raise UnsupportedStatement(f"Task '{fq}' does not exist or not authorized.")
        db, sch, nm = fq.split(".")
        now = self.clock()
        self.con.execute(
            "INSERT INTO TASK_HISTORY (NAME, DATABASE_NAME, SCHEMA_NAME, FQ_NAME, STATE, SCHEDULED_TIME, QUERY_START_TIME, "
            "COMPLETED_TIME, ROOT_TASK_ID, RUN_ID, ATTEMPT_NUMBER) VALUES (?, ?, ?, ?, 'SUCCEEDED', ?, ?, ?, ?, ?, 1)",
            [nm, db, sch, fq, now, now, now, fq, f"manual-{len(self.executed) + 1}"])
        return True

    def _table_tag(self, stmt: str) -> bool:
        m = re.match(rf"^ALTER\s+TABLE\s+({IDENT})\s+SET\s+TAG\s+({IDENT})\s*=\s*'([^']*)'$", stmt, re.I)
        u = re.match(rf"^ALTER\s+TABLE\s+({IDENT})\s+UNSET\s+TAG\s+({IDENT})$", stmt, re.I)
        if not m and not u:
            return False
        table, tag = (m or u).group(1).upper(), (m or u).group(2).upper()
        tparts, gparts = table.split("."), tag.split(".")
        if len(tparts) != 3 or len(gparts) != 3:
            raise UnsupportedStatement("tag statements need fully qualified table and tag names")
        key = [gparts[2], tparts[0], tparts[1], tparts[2]]
        self.con.execute("DELETE FROM TAG_REFERENCES WHERE TAG_NAME = ? AND OBJECT_DATABASE = ? AND OBJECT_SCHEMA = ? "
                         "AND OBJECT_NAME = ? AND COLUMN_NAME IS NULL AND DOMAIN = 'TABLE'", key)
        if m:
            self.con.execute(
                "INSERT INTO TAG_REFERENCES VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 'TABLE')",
                [gparts[0], gparts[1], gparts[2], m.group(3), tparts[0], tparts[1], tparts[2]])
        return True


# --------------------------------------------------------------------------- live account
class LiveExecutor:
    """Runs rendered SQL through a DB-API 2.0 connection opened as the agent's service identity."""

    _SHOW_MAP = {"size": "warehouse_size", "auto_suspend": "auto_suspend", "max_cluster_count": "max_cluster_count",
                 "min_cluster_count": "min_cluster_count", "auto_resume": "auto_resume", "disabled": "disabled"}

    def __init__(self, connection: Any, dry_run: bool = False):
        self.connection = connection
        self.dry_run = dry_run
        self.executed: list[str] = []

    def run(self, sql: str) -> None:
        if not self.dry_run:
            cur = self.connection.cursor()
            try:
                cur.execute(sql)
            finally:
                close = getattr(cur, "close", None)
                if close:
                    close()
        self.executed.append(sql)

    def current(self, object_type: str, name: str) -> dict:
        validate_value(name, "identifier", "name")
        show = {"warehouse": "SHOW WAREHOUSES LIKE %s", "user": "SHOW USERS LIKE %s"}.get(object_type)
        if show is None:
            return {}
        cur = self.connection.cursor()
        cur.execute(show, (name.split(".")[-1],))
        cols = [d[0].lower() for d in cur.description]
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            if str(rec.get("name", "")).upper() == name.split(".")[-1].upper():
                out = {}
                for src, dst in self._SHOW_MAP.items():
                    if src in rec:
                        out[dst] = _coerce(rec[src], dst)
                return out
        raise ActionRefused(f"{object_type} {name} not found in the live account")


def _coerce(v: Any, prop: str) -> Any:
    kind = CAPTURE_KINDS.get(prop)
    if kind == "integer" and v is not None:
        return int(v)
    if kind == "boolean" and isinstance(v, str):
        return v.strip().lower() == "true"
    if kind == "warehouse_size" and isinstance(v, str):
        return v.upper().replace("-", "").replace(" ", "")
    return v
