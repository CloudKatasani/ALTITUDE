"""Statement analysis for the read-only guarantees (principle 6).

Two uses:
- ``assert_read_only(sql)`` — the live harvester refuses anything but a single SELECT / SHOW / DESCRIBE.
- ``analyse_bootstrap(sql)`` — the access-bootstrap kill-test: parses every statement with sqlglot and
  reports privileged roles, write privileges and objects created outside the diagnostics namespace.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp

from altitude.core.errors import ReadOnlyViolation

logging.getLogger("sqlglot").setLevel(logging.ERROR)

_PLACEHOLDER = re.compile(r"%\((\w+)\)s|%s|\?")
_SHOW_BODY = re.compile(r"(?i)[A-Z0-9_ .$\"]+(\s+LIKE\s+'[^';]*')?(\s+IN\s+[A-Z0-9_ .$\"]+)?")
_SIDE_EFFECT_FUNCS =re.compile(r"(?i)\bSYSTEM\$(?!(?:ALLOWLIST|CLUSTERING_INFORMATION|TYPEOF|GET_TAG)\b)\w+")
READ_STATEMENTS = (exp.Select, exp.Show, exp.Describe, exp.Union, exp.Intersect, exp.Except)
PRIVILEGED_ROLES = {"ACCOUNTADMIN", "ORGADMIN", "GLOBALORGADMIN"}
WRITE_PRIVILEGES = {
    "INSERT", "UPDATE", "DELETE", "TRUNCATE", "OWNERSHIP", "ALL", "ALL PRIVILEGES", "MODIFY", "OPERATE", "APPLY",
    "CREATE", "CREATE TABLE", "CREATE SCHEMA", "CREATE DATABASE", "CREATE VIEW", "CREATE STAGE", "CREATE TASK",
    "CREATE PIPE", "CREATE STREAM", "CREATE ROLE", "CREATE USER", "CREATE WAREHOUSE", "MANAGE GRANTS",
    "EXECUTE TASK", "EXECUTE ALERT", "IMPORTED PRIVILEGES", "REFERENCES", "REBUILD", "EVOLVE SCHEMA",
}
ALLOWED_PRIVILEGES = {"USAGE", "MONITOR", "MONITOR USAGE", "MONITOR EXECUTION"}
DML_COMMANDS = {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "COPY", "PUT", "REMOVE", "CALL", "EXECUTE"}


def _neutralise(sql: str) -> str:
    return _PLACEHOLDER.sub("NULL", sql)


def parse(sql: str, dialect: str = "snowflake") -> list[exp.Expression]:
    return [s for s in sqlglot.parse(_neutralise(sql), read=dialect) if s is not None]


def assert_read_only(sql: str, dialect: str = "snowflake") -> exp.Expression:
    """Raise ``ReadOnlyViolation`` unless ``sql`` is exactly one read statement without side effects."""
    try:
        statements = parse(sql, dialect)
    except sqlglot.errors.ParseError as e:
        raise ReadOnlyViolation(f"refusing unparseable statement: {e}") from e
    if len(statements) != 1:
        raise ReadOnlyViolation(f"refusing {len(statements)} statements; exactly one read statement is allowed")
    st = statements[0]
    if isinstance(st, exp.Command) and str(st.this).upper() in {"SHOW", "DESCRIBE", "DESC"}:
        # sqlglot parses most SHOW variants as a generic Command: accept only a plain object listing.
        if not _SHOW_BODY.fullmatch(str(st.expression or "").strip()):
            raise ReadOnlyViolation(f"refusing unusual {st.this} statement: {sql.strip()[:80]}")
        return st
    if not isinstance(st, READ_STATEMENTS):
        raise ReadOnlyViolation(f"refusing non-read statement ({type(st).__name__}): {sql.strip()[:80]}")
    if isinstance(st, exp.Select) and st.args.get("into") is not None:
        raise ReadOnlyViolation("refusing SELECT ... INTO")
    for node in st.walk():
        if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
                             exp.TruncateTable, exp.Command)):
            raise ReadOnlyViolation(f"refusing statement with embedded {type(node).__name__}")
    if _SIDE_EFFECT_FUNCS.search(sql):
        raise ReadOnlyViolation("refusing SYSTEM$ function with possible side effects")
    return st


# --------------------------------------------------------------------------- bootstrap analysis


@dataclass
class StatementInfo:
    verb: str                   # USE | CREATE | ALTER | GRANT | REVOKE | DROP | SELECT | SHOW | ...
    object_kind: str = ""       # ROLE | WAREHOUSE | RESOURCE MONITOR | USER | DATABASE ROLE | ...
    object_name: str = ""
    privileges: list[str] = field(default_factory=list)
    grantee: str = ""
    sql: str = ""


_KINDS = ("RESOURCE MONITOR", "DATABASE ROLE", "NETWORK POLICY", "WAREHOUSE", "ROLE", "USER", "SCHEMA", "DATABASE",
          "TABLE", "VIEW", "TASK", "STAGE", "PIPE", "INTEGRATION")


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z_$][A-Za-z0-9_$.\"]*|'[^']*'|=|\(|\)|,", text)


def _name_after(words: list[str], i: int) -> str:
    j = i
    while j < len(words) and words[j].upper() in {"IF", "NOT", "EXISTS", "OR", "REPLACE"}:
        j += 1
    return words[j].strip('"') if j < len(words) else ""


def _kind_and_name(rest: str) -> tuple[str, str]:
    rest = rest.strip()
    up = rest.upper()
    for k in _KINDS:
        if up.startswith(k + " ") or up == k:
            words = _words(rest[len(k):])
            return k, _name_after(words, 0)
    words = _words(rest)
    return (words[0].upper() if words else ""), (_name_after(words, 1) if len(words) > 1 else "")


def describe(st: exp.Expression) -> StatementInfo:
    text = st.sql(dialect="snowflake")
    if isinstance(st, exp.Grant):
        privs = [p.sql(dialect="snowflake").upper() for p in st.args.get("privileges") or []]
        principals = [p.sql(dialect="snowflake") for p in st.args.get("principals") or []]
        securable = st.args.get("securable")
        return StatementInfo("GRANT", (st.args.get("kind") or "").upper(),
                             securable.sql(dialect="snowflake") if securable is not None else "",
                             privs, " ".join(principals), text)
    if isinstance(st, exp.Use):
        kind = (st.args.get("kind").sql() if st.args.get("kind") is not None else "").upper()
        return StatementInfo("USE", kind, st.this.sql(dialect="snowflake") if st.this is not None else "", sql=text)
    if isinstance(st, exp.Command):
        verb = str(st.this).upper()
        rest = str(st.expression or "")
        if verb in {"GRANT", "REVOKE"}:
            m = re.match(r"(?is)\s*(.*?)\s+(?:TO|FROM)\s+(.*)$", rest)
            what, grantee = (m.group(1), m.group(2)) if m else (rest, "")
            up = what.upper().strip()
            if up.startswith("DATABASE ROLE "):
                return StatementInfo(verb, "DATABASE ROLE", what.strip()[len("DATABASE ROLE "):].strip(),
                                     ["DATABASE ROLE"], grantee.strip(), text)
            if up.startswith("ROLE "):
                return StatementInfo(verb, "ROLE", what.strip()[len("ROLE "):].strip(), ["ROLE"], grantee.strip(), text)
            pm = re.match(r"(?is)(.*?)\s+ON\s+(.*)$", what)
            privs = [p.strip().upper() for p in (pm.group(1) if pm else what).split(",")]
            target = pm.group(2).strip() if pm else ""
            kind, name = _kind_and_name(target) if target else ("", "")
            return StatementInfo(verb, kind, name, privs, grantee.strip(), text)
        if verb in {"CREATE", "ALTER", "DROP"}:
            body = re.sub(r"(?i)^\s*OR\s+REPLACE\s+", "", rest)
            kind, name = _kind_and_name(body)
            return StatementInfo(verb, kind, name, sql=text)
        return StatementInfo(verb, sql=text)
    if isinstance(st, (exp.Create, exp.Drop, exp.Alter)):
        verb = {exp.Create: "CREATE", exp.Drop: "DROP", exp.Alter: "ALTER"}[type(st)]
        kind = str(st.args.get("kind") or "").upper()
        target = st.this
        name = target.sql(dialect="snowflake") if target is not None else ""
        name = re.split(r"\s|\(", name)[0]
        return StatementInfo(verb, kind, name, sql=text)
    return StatementInfo(type(st).__name__.upper(), sql=text)


def analyse_bootstrap(sql: str, *, namespace_prefix: str, allowed_admin_roles: set[str]) -> list[str]:
    """Kill-test: return every violation of the least-privilege contract (empty list ⇒ compliant)."""
    problems: list[str] = []
    if re.search(r"(?i)\b(" + "|".join(PRIVILEGED_ROLES) + r")\b", sql):
        problems.append("privileged role (e.g. ACCOUNTADMIN) referenced in the bootstrap")
    try:
        statements = parse(sql)
    except sqlglot.errors.ParseError as e:
        return problems + [f"bootstrap does not parse: {e}"]
    prefix = namespace_prefix.upper()
    for st in statements:
        info = describe(st)
        head = info.sql.split("\n")[0][:90]
        if info.verb in DML_COMMANDS or isinstance(st, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.TruncateTable)):
            problems.append(f"data-modifying statement: {head}")
        elif info.verb == "USE":
            if info.object_kind == "ROLE" and info.object_name.upper() not in allowed_admin_roles | {f"{prefix}ROLE"}:
                problems.append(f"USE ROLE {info.object_name} is not an allowed administrative role")
        elif info.verb in {"CREATE", "ALTER"}:
            if not info.object_name.upper().strip('"').startswith(prefix):
                problems.append(f"{info.verb} {info.object_kind} {info.object_name} is outside the {prefix}* namespace")
        elif info.verb == "DROP":
            problems.append(f"DROP in bootstrap: {head}")
        elif info.verb == "GRANT":
            grantee = info.grantee.upper()
            if not re.search(rf"\b{re.escape(prefix)}\w+", grantee):
                problems.append(f"grant to a principal outside the diagnostics namespace: {head}")
            if info.object_kind == "DATABASE ROLE":
                if not info.object_name.upper().startswith("SNOWFLAKE.") or not info.object_name.upper().endswith("_VIEWER"):
                    problems.append(f"database role {info.object_name} is not a SNOWFLAKE.*_VIEWER role")
            elif info.object_kind == "ROLE":
                if not info.object_name.upper().startswith(prefix):
                    problems.append(f"grants role {info.object_name} (only the diagnostics role may be granted)")
            else:
                for p in info.privileges:
                    if p in WRITE_PRIVILEGES or p not in ALLOWED_PRIVILEGES:
                        problems.append(f"privilege {p} is not read-only: {head}")
                if "USAGE" in info.privileges and info.object_kind not in {"WAREHOUSE", ""}:
                    problems.append(f"USAGE granted on {info.object_kind} {info.object_name} (only the diagnostics warehouse)")
                if info.object_kind == "WAREHOUSE" and not info.object_name.upper().startswith(prefix):
                    problems.append(f"grant on client warehouse {info.object_name}")
        elif info.verb in {"REVOKE"}:
            problems.append(f"REVOKE in bootstrap: {head}")
        elif not isinstance(st, READ_STATEMENTS):
            problems.append(f"unexpected statement {info.verb}: {head}")
    return problems
