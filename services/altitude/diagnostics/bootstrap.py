"""Least-privilege access bootstrap for Package D (Section 6.10).

Generates, from one statement list (so SQL and manifest never drift):

- ``bootstrap_sql``      a dedicated read-only role granted the ``SNOWFLAKE`` database roles
                         (USAGE_VIEWER, GOVERNANCE_VIEWER, OBJECT_VIEWER, SECURITY_VIEWER) plus MONITOR USAGE /
                         MONITOR EXECUTION for SHOW-based sources; an X-Small diagnostics warehouse with a resource
                         monitor capped at ``rubric.diagnostics.access.credit_budget``; a key-pair service user.
- ``teardown_sql``       revoke everything, drop the principal and warehouse, and the access-log query handed to
                         the client at close.
- ``permission_manifest`` every privilege with the reason it is needed and the evidence it unlocks.

No account-administrator role is used or granted anywhere, and no privilege on any client object is
requested; :func:`kill_test` proves it by parsing the generated SQL with sqlglot.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from altitude.core.rubric import RubricSet, default_rubrics

from .readonly import analyse_bootstrap

DATABASE_ROLES = {
    "USAGE_VIEWER": "Metering, warehouse load, storage, task/copy/pipe and serverless histories (cost, performance, reliability).",
    "GOVERNANCE_VIEWER": "Query history, access history, tag and policy references, data metric function references.",
    "OBJECT_VIEWER": "Object inventory: tables, columns, views, dependencies, semantic views, search services.",
    "SECURITY_VIEWER": "Users, roles, grants, login history and network policies.",
}
ADMIN_ROLES = {"SECURITYADMIN", "SYSADMIN", "USERADMIN"}


@dataclass
class BootstrapConfig:
    prefix: str = "ALTITUDE_DIAG_"
    security_admin_role: str = "SECURITYADMIN"     # role creation, grants (MANAGE GRANTS)
    sysadmin_role: str = "SYSADMIN"                # warehouse creation
    monitor_admin_role: str = "SYSADMIN"           # resource monitor creation (see manifest note)
    user_admin_role: str = "USERADMIN"             # service user creation
    credit_budget: float | None = None             # defaults to rubric.diagnostics.access.credit_budget
    public_key: str = "<RSA_PUBLIC_KEY_FROM_CLIENT_VAULT>"
    database_roles: list[str] = field(default_factory=lambda: list(DATABASE_ROLES))

    @property
    def role(self) -> str:
        return f"{self.prefix}ROLE"

    @property
    def warehouse(self) -> str:
        return f"{self.prefix}WH"

    @property
    def monitor(self) -> str:
        return f"{self.prefix}RM"

    @property
    def user(self) -> str:
        return f"{self.prefix}SVC"


@dataclass(frozen=True)
class Step:
    sql: str
    privilege: str = ""
    on: str = ""
    why: str = ""
    section: str = ""


def _steps(cfg: BootstrapConfig, rubrics: RubricSet) -> list[Step]:
    budget = cfg.credit_budget if cfg.credit_budget is not None else rubrics.get("rubric.diagnostics.access.credit_budget")
    notify = rubrics.get("rubric.diagnostics.access.notify_at_percent")
    suspend = rubrics.get("rubric.diagnostics.access.suspend_at_percent")
    timeout = rubrics.get("rubric.diagnostics.access.statement_timeout_seconds")
    auto_suspend = rubrics.get("rubric.diagnostics.access.auto_suspend_seconds")
    budget_txt = f"{float(budget):g}"
    s: list[Step] = [
        Step(f"USE ROLE {cfg.security_admin_role}", section="1. Read-only diagnostics role (run as a grants administrator)"),
        Step(f"CREATE ROLE IF NOT EXISTS {cfg.role} COMMENT = 'Read-only metadata diagnostics (Package D); revoked at close'",
             "CREATE ROLE", "account", "Dedicated, revocable principal so access is isolated and auditable."),
    ]
    for dr in cfg.database_roles:
        s.append(Step(f"GRANT DATABASE ROLE SNOWFLAKE.{dr} TO ROLE {cfg.role}", f"DATABASE ROLE SNOWFLAKE.{dr}",
                      "SNOWFLAKE database", DATABASE_ROLES.get(dr, "Read-only ACCOUNT_USAGE views.")))
    s += [
        Step(f"GRANT MONITOR USAGE ON ACCOUNT TO ROLE {cfg.role}", "MONITOR USAGE", "account",
             "SHOW WAREHOUSES / RESOURCE MONITORS / REPLICATION GROUPS see every object (configuration only, no data)."),
        Step(f"GRANT MONITOR EXECUTION ON ACCOUNT TO ROLE {cfg.role}", "MONITOR EXECUTION", "account",
             "SHOW TASKS / ALERTS across the account (definitions and state; cannot run or change them)."),
        Step(f"USE ROLE {cfg.sysadmin_role}", section="2. Credit-capped X-Small diagnostics warehouse"),
        Step(f"CREATE WAREHOUSE IF NOT EXISTS {cfg.warehouse} WITH WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = {auto_suspend} "
             f"AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE STATEMENT_TIMEOUT_IN_SECONDS = {timeout} "
             "COMMENT = 'Package D diagnostics; dropped at close'",
             "CREATE WAREHOUSE", "account", "Isolated compute so diagnostics never consume or queue on client warehouses."),
        Step(f"USE ROLE {cfg.monitor_admin_role}", section="3. Resource monitor capped at the agreed credit budget"),
        Step(f"CREATE RESOURCE MONITOR IF NOT EXISTS {cfg.monitor} WITH CREDIT_QUOTA = {budget_txt} FREQUENCY = NEVER "
             f"START_TIMESTAMP = IMMEDIATELY TRIGGERS ON {notify} PERCENT DO NOTIFY ON {suspend} PERCENT DO SUSPEND_IMMEDIATE",
             "CREATE RESOURCE MONITOR", "account", f"Hard cap of {budget_txt} credits agreed upfront (rubric.diagnostics.access.credit_budget)."),
        Step(f"ALTER WAREHOUSE {cfg.warehouse} SET RESOURCE_MONITOR = {cfg.monitor}", "", "", ""),
        Step(f"USE ROLE {cfg.security_admin_role}", section="4. Warehouse usage for the diagnostics role only"),
        Step(f"GRANT USAGE ON WAREHOUSE {cfg.warehouse} TO ROLE {cfg.role}", "USAGE", f"WAREHOUSE {cfg.warehouse}",
             "Run the read-only harvest queries on the capped diagnostics warehouse (and no other)."),
        Step(f"USE ROLE {cfg.user_admin_role}", section="5. Key-pair service user (no password)"),
        Step(f"CREATE USER IF NOT EXISTS {cfg.user} TYPE = SERVICE DEFAULT_ROLE = {cfg.role} DEFAULT_WAREHOUSE = {cfg.warehouse} "
             f"RSA_PUBLIC_KEY = '{cfg.public_key}' COMMENT = 'Package D diagnostics service user; disabled at close'",
             "CREATE USER", "account", "Key-pair authenticated service identity; no password, no interactive login."),
        Step(f"USE ROLE {cfg.security_admin_role}", section="6. Bind the role to the service user"),
        Step(f"GRANT ROLE {cfg.role} TO USER {cfg.user}", f"ROLE {cfg.role}", f"USER {cfg.user}",
             "The service user can only assume the read-only diagnostics role."),
    ]
    return s


def bootstrap_sql(cfg: BootstrapConfig | None = None, rubrics: RubricSet | None = None) -> str:
    cfg = cfg or BootstrapConfig()
    rubrics = rubrics or default_rubrics()
    lines = [
        "-- Package D access bootstrap: least-privilege, metadata-only, revocable.",
        f"-- Principal: role {cfg.role}, user {cfg.user} (key-pair), warehouse {cfg.warehouse} capped by {cfg.monitor}.",
        "-- Uses only grants-, system- and user-administration roles; requests no privilege on any client database,",
        "-- schema, table or warehouse. Verify SNOWFLAKE database role names against current documentation.",
    ]
    for st in _steps(cfg, rubrics):
        if st.section:
            lines += ["", f"-- {st.section}"]
        lines.append(st.sql + ";")
    return "\n".join(lines) + "\n"


def teardown_sql(cfg: BootstrapConfig | None = None) -> str:
    cfg = cfg or BootstrapConfig()
    lines = [
        "-- Package D close-out: hand over the access log, then revoke and drop every diagnostics object.",
        "",
        "-- 1. Access log for the client (everything the diagnostics principal did)",
        f"SELECT EVENT_TIMESTAMP, USER_NAME, CLIENT_IP, FIRST_AUTHENTICATION_FACTOR, IS_SUCCESS "
        f"FROM SNOWFLAKE.ACCOUNT_USAGE.LOGIN_HISTORY WHERE USER_NAME = '{cfg.user}' ORDER BY EVENT_TIMESTAMP;",
        f"SELECT START_TIME, QUERY_TYPE, WAREHOUSE_NAME, ROLE_NAME, QUERY_TEXT "
        f"FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY WHERE USER_NAME = '{cfg.user}' ORDER BY START_TIME;",
        "",
        "-- 2. Disable and drop the service user",
        f"USE ROLE {cfg.user_admin_role};",
        f"ALTER USER IF EXISTS {cfg.user} SET DISABLED = TRUE;",
        f"DROP USER IF EXISTS {cfg.user};",
        "",
        "-- 3. Revoke and drop the role",
        f"USE ROLE {cfg.security_admin_role};",
        f"REVOKE USAGE ON WAREHOUSE {cfg.warehouse} FROM ROLE {cfg.role};",
        f"REVOKE MONITOR EXECUTION ON ACCOUNT FROM ROLE {cfg.role};",
        f"REVOKE MONITOR USAGE ON ACCOUNT FROM ROLE {cfg.role};",
    ]
    for dr in cfg.database_roles:
        lines.append(f"REVOKE DATABASE ROLE SNOWFLAKE.{dr} FROM ROLE {cfg.role};")
    lines += [
        f"DROP ROLE IF EXISTS {cfg.role};",
        "",
        "-- 4. Drop the diagnostics warehouse and its resource monitor",
        f"USE ROLE {cfg.sysadmin_role};",
        f"DROP WAREHOUSE IF EXISTS {cfg.warehouse};",
        f"USE ROLE {cfg.monitor_admin_role};",
        f"DROP RESOURCE MONITOR IF EXISTS {cfg.monitor};",
    ]
    return "\n".join(lines) + "\n"


def permission_manifest(cfg: BootstrapConfig | None = None, rubrics: RubricSet | None = None) -> dict:
    from .harvest import CLIENT_SUPPLIED, HARVEST_QUERIES

    cfg = cfg or BootstrapConfig()
    rubrics = rubrics or default_rubrics()
    privileges = [
        {"privilege": st.privilege, "on": st.on, "granted_to": cfg.role if st.privilege.startswith(("DATABASE", "MONITOR", "USAGE"))
         else (cfg.user if st.privilege.startswith("ROLE") else "(setup)"), "why": st.why, "read_only": True,
         "statement": st.sql}
        for st in _steps(cfg, rubrics) if st.privilege
    ]
    by_role: dict[str, list[str]] = {}
    for t, q in sorted(HARVEST_QUERIES.items()):
        by_role.setdefault(q.database_role, []).append(t)
    return {
        "principal": {"role": cfg.role, "user": cfg.user, "warehouse": cfg.warehouse, "resource_monitor": cfg.monitor,
                      "authentication": "key-pair (RSA); no password"},
        "credit_cap": {"credits": rubrics.get("rubric.diagnostics.access.credit_budget"),
                       "rubric_ref": "rubric.diagnostics.access.credit_budget",
                       "notify_at_percent": rubrics.get("rubric.diagnostics.access.notify_at_percent"),
                       "suspend_at_percent": rubrics.get("rubric.diagnostics.access.suspend_at_percent")},
        "administrative_roles_used": sorted({cfg.security_admin_role, cfg.sysadmin_role, cfg.monitor_admin_role,
                                             cfg.user_admin_role}),
        "privileges": privileges,
        "evidence_unlocked": {role: tables for role, tables in sorted(by_role.items())},
        "client_supplied": sorted(CLIENT_SUPPLIED),
        "never_requested": [
            "account administrator or organisation administrator roles",
            "any privilege on client databases, schemas, tables, views or stages (no SELECT on row data)",
            "INSERT / UPDATE / DELETE / TRUNCATE / OWNERSHIP / MODIFY / OPERATE on any client object",
            "USAGE on client warehouses",
        ],
        "data_handling": "Metadata only: ACCOUNT_USAGE / SHOW output. Row data never leaves the account.",
        "close_out": "teardown.sql: hand over the access log, then revoke and drop every diagnostics object.",
        "notes": [
            "Verify SNOWFLAKE database role names and view availability (edition) against current documentation.",
            "Some accounts restrict CREATE RESOURCE MONITOR to the account owner: the platform owner then runs "
            "section 3 under their own change process; the diagnostics principal still never receives elevated roles.",
            "DATA_QUALITY_MONITORING_RESULTS needs the optional SNOWFLAKE.DATA_QUALITY_MONITORING_VIEWER application "
            "role; without it the source is recorded as unavailable and confidence is lowered.",
        ],
    }


def kill_test(sql: str | None = None, cfg: BootstrapConfig | None = None) -> list[str]:
    """Return every least-privilege violation in the bootstrap (empty ⇒ the harness runs without elevation)."""
    cfg = cfg or BootstrapConfig()
    return analyse_bootstrap(sql if sql is not None else bootstrap_sql(cfg), namespace_prefix=cfg.prefix,
                             allowed_admin_roles=ADMIN_ROLES)
