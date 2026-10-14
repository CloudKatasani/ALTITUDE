"""Read-only connection wrapper (principle 6: source is never modified).

Every statement that reaches a source system goes through
:func:`classify_statement` first:

1. an independent tokenizer (comments and literals removed, no reliance on the
   SQL parser) rejects multi-statement batches, executable comments,
   unterminated literals, any non-read leading keyword and any write/DDL/DCL or
   side-effecting keyword anywhere in the statement;
2. sqlglot parses the statement in the source dialect; the root must be a query
   (SELECT/WITH/set operation), DESCRIBE, SHOW or EXPLAIN and no write node
   (INSERT/UPDATE/DELETE/MERGE/CREATE/DROP/ALTER/TRUNCATE/GRANT/SELECT INTO/
   locking reads/EXEC) may appear anywhere in the tree;
3. when a scope (the permission manifest's ``objects_read``) is supplied, every
   object the statement reads must be listed — a harvester physically cannot
   read user tables, so no row data can be harvested.

Anything else raises :class:`~altitude.core.errors.ReadOnlyViolation` *before*
the driver sees the statement. Every statement, allowed or refused, is logged.
The wrapper exposes no write path: ``executemany``/``callproc`` are refused,
``commit`` is a no-op, and the underlying connection is not reachable through
the public API.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence

import sqlglot
from sqlglot import exp

from altitude.core.errors import ReadOnlyViolation

log = logging.getLogger("altitude.connectors.readonly")

#: ALTITUDE source names → sqlglot dialects.
DIALECTS = {
    "sqlserver": "tsql",
    "tsql": "tsql",
    "oracle": "oracle",
    "teradata": "teradata",
    "snowflake": "snowflake",
    "duckdb": "duckdb",
    "postgres": "postgres",
}

ALLOWED_LEADING = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN"}
DIALECT_LEADING = {"teradata": {"SEL", "HELP"}}

# Keywords that can only appear in statements that change state (data, schema,
# privileges, session/transaction state) or run arbitrary code.
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "MERGE", "UPSERT", "CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME",
    "GRANT", "REVOKE", "DENY", "EXEC", "EXECUTE", "CALL", "INTO", "COPY", "UNLOAD", "PUT", "REMOVE",
    "LOCK", "SET", "DECLARE", "BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "BACKUP", "RESTORE", "KILL",
    "SHUTDOWN", "DBCC", "BULK", "RECONFIGURE", "USE", "IMPORT", "EXPORT", "COMMENT", "VACUUM", "ANALYZE",
    "REFRESH", "UNDROP", "PURGE", "FLASHBACK", "NEXTVAL", "SETVAL",
}
DIALECT_FORBIDDEN = {
    "teradata": {"INS", "UPD", "DEL", "CT", "CV", "REPLACE", "MLOAD", "FASTLOAD", "COLLECT", "LOCKING", "DATABASE"},
    "tsql": {"GO", "WAITFOR", "OPENQUERY", "OPENROWSET", "OPENDATASOURCE", "XP_CMDSHELL", "SP_EXECUTESQL",
             "SP_CONFIGURE", "OUTPUT", "UPDLOCK", "XLOCK", "TABLOCKX", "HOLDLOCK", "ROWLOCK", "PAGLOCK"},
    "oracle": {"REPLACE", "DBMS_SQL", "DBMS_SCHEDULER", "DBMS_JOB", "UTL_FILE", "UTL_HTTP", "UTL_TCP",
               "DBMS_PIPE", "AUTONOMOUS_TRANSACTION"},
}
# A REPLACE immediately followed by "(" is the string function, not REPLACE VIEW/PROCEDURE.
FUNCTION_EXEMPT = {"REPLACE"}

READ_COMMANDS = {"SHOW", "EXPLAIN", "DESCRIBE", "DESC", "HELP"}

_WRITE_NODES: tuple[type, ...] = tuple(
    t for t in (
        getattr(exp, n, None)
        for n in ("Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable", "Grant",
                  "Revoke", "Into", "Lock", "Execute", "Set", "Transaction", "Commit", "Rollback", "Copy",
                  "Use", "Analyze", "LoadData", "Pragma", "Attach", "Detach", "Export", "Refresh", "Summarize",
                  "Kill", "Comment", "Declare", "Command")
    ) if t is not None
)


# --------------------------------------------------------------------------- tokenizer


@dataclass(frozen=True)
class Token:
    kind: str  # word | punct | string | qident | number
    text: str
    pos: int


def tokenize(sql: str, dialect: str = "tsql") -> list[Token]:
    """Tokenize SQL without a parser. Comments are dropped; literals are opaque.

    Raises ReadOnlyViolation on anything that could hide code from analysis:
    executable/optimizer comments carrying statements, unterminated comments or
    literals, and NUL bytes.
    """
    if "\x00" in sql:
        raise ReadOnlyViolation("NUL byte in statement")
    out: list[Token] = []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c.isspace():
            i += 1
        elif sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j + 1
        elif sql.startswith("/*", i):
            if sql.startswith("/*!", i):
                raise ReadOnlyViolation("executable comment (/*! ... */) is not permitted")
            j = sql.find("*/", i + 2)
            if j < 0:
                raise ReadOnlyViolation("unterminated block comment")
            i = j + 2
        elif c == "'" or (c in "nN" and sql.startswith("'", i + 1)):
            start = i
            i = i + 2 if c != "'" else i + 1
            while True:
                j = sql.find("'", i)
                if j < 0:
                    raise ReadOnlyViolation("unterminated string literal")
                if sql.startswith("''", j):
                    i = j + 2
                    continue
                i = j + 1
                break
            out.append(Token("string", sql[start:i], start))
        elif c in '"[`':
            close = {"[": "]", '"': '"', "`": "`"}[c]
            j = sql.find(close, i + 1)
            if j < 0:
                raise ReadOnlyViolation("unterminated quoted identifier")
            out.append(Token("qident", sql[i + 1:j], i))
            i = j + 1
        elif c.isalpha() or c in "_@#$":
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] in "_@#$"):
                j += 1
            out.append(Token("word", sql[i:j], i))
            i = j
        elif c.isdigit():
            j = i + 1
            while j < n and (sql[j].isalnum() or sql[j] == "."):
                j += 1
            out.append(Token("number", sql[i:j], i))
            i = j
        else:
            out.append(Token("punct", c, i))
            i += 1
    return out


def split_statements(tokens: Sequence[Token]) -> list[list[Token]]:
    stmts: list[list[Token]] = [[]]
    for t in tokens:
        if t.kind == "punct" and t.text == ";":
            stmts.append([])
        else:
            stmts[-1].append(t)
    return [s for s in stmts if s]


# --------------------------------------------------------------------------- classification


@dataclass
class Verdict:
    sql: str
    dialect: str
    kind: str  # select | show | describe | explain | help
    objects: list[str] = field(default_factory=list)
    parser: str = "sqlglot"


def _sg_dialect(dialect: str) -> str:
    try:
        return DIALECTS[dialect.lower()]
    except KeyError:
        raise ValueError(f"unknown source dialect {dialect!r}") from None


def _keyword_check(stmt: list[Token], dialect: str) -> str:
    """Return the leading keyword; raise on any forbidden keyword."""
    words = [t for t in stmt if t.kind != "punct" or t.text not in "()"]
    if not words or words[0].kind != "word":
        raise ReadOnlyViolation("statement does not start with a read keyword")
    lead = words[0].text.upper()
    allowed = ALLOWED_LEADING | DIALECT_LEADING.get(dialect, set())
    if lead not in allowed:
        raise ReadOnlyViolation(f"'{lead}' statements are not permitted on a read-only connection")
    forbidden = FORBIDDEN_KEYWORDS | DIALECT_FORBIDDEN.get(dialect, set())
    for idx, t in enumerate(stmt):
        if t.kind != "word":
            continue
        up = t.text.upper()
        nxt = stmt[idx + 1] if idx + 1 < len(stmt) else None
        if up == "FOR" and nxt is not None and nxt.kind == "word" and nxt.text.upper() == "UPDATE":
            raise ReadOnlyViolation("locking read (FOR UPDATE) is not permitted")
        if up in forbidden:
            if up in FUNCTION_EXEMPT and nxt is not None and nxt.text == "(":
                continue
            raise ReadOnlyViolation(f"keyword '{up}' is not permitted on a read-only connection")
        if up.startswith("SYSTEM$") or (dialect == "tsql" and up.startswith(("XP_", "SP_"))):
            raise ReadOnlyViolation(f"system procedure/function '{t.text}' is not permitted")
    return lead


def _objects_read(tree: exp.Expression) -> list[str]:
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    names = set()
    for t in tree.find_all(exp.Table):
        if not t.name:
            continue
        parts = [p for p in (t.catalog, t.db, t.name) if p]
        fq = ".".join(parts)
        if len(parts) == 1 and fq.lower() in ctes:
            continue
        names.add(fq)
    return sorted(names, key=str.lower)


def _quiet_parse(sql: str, dialect: str) -> list[exp.Expression | None]:
    logger = logging.getLogger("sqlglot")
    level = logger.level
    logger.setLevel(logging.ERROR)
    try:
        return sqlglot.parse(sql, read=dialect)
    finally:
        logger.setLevel(level)


def classify_statement(sql: str, dialect: str, scope: Iterable[str] | None = None) -> Verdict:
    """Return a :class:`Verdict` for a read statement or raise ReadOnlyViolation."""
    if not isinstance(sql, str) or not sql.strip():
        raise ReadOnlyViolation("empty statement")
    dialect = dialect.lower()
    sg = _sg_dialect(dialect)
    stmts = split_statements(tokenize(sql, sg))
    if len(stmts) != 1:
        raise ReadOnlyViolation(f"exactly one statement is permitted per call (got {len(stmts)})")
    lead = _keyword_check(stmts[0], sg)

    verdict = Verdict(sql=sql, dialect=dialect, kind="select")
    try:
        trees = [t for t in _quiet_parse(sql, sg) if t is not None]
    except (sqlglot.errors.ParseError, sqlglot.errors.TokenError):
        trees = []
    if trees:
        if len(trees) != 1:
            raise ReadOnlyViolation("parser found more than one statement")
        tree = trees[0]
        if isinstance(tree, exp.Command):
            cmd = str(tree.this).upper()
            if cmd not in READ_COMMANDS:
                raise ReadOnlyViolation(f"command '{cmd}' is not permitted")
            verdict.kind = cmd.lower()
            if cmd == "EXPLAIN":
                inner = str(tree.expression.this if isinstance(tree.expression, exp.Literal) else tree.expression or "")
                inner = re.sub(r"^\s*(ANALYZE|VERBOSE|PLAN\s+FOR)\s+", "", inner, flags=re.IGNORECASE)
                if inner.strip():
                    verdict.objects = classify_statement(inner, dialect, scope).objects
                return verdict
            if scope is not None:
                raise ReadOnlyViolation(f"cannot verify the objects read by '{cmd}' against the permission manifest")
            verdict.parser = "tokenizer"
            return verdict
        show = getattr(exp, "Show", None)
        if show is not None and isinstance(tree, show):
            if scope is not None:
                raise ReadOnlyViolation("cannot verify the objects read by SHOW against the permission manifest")
            verdict.kind = "show"
            return verdict
        if isinstance(tree, exp.Describe):
            verdict.kind = "describe"
        elif not isinstance(tree, exp.Query):
            raise ReadOnlyViolation(f"{type(tree).__name__} statements are not permitted")
        for node in tree.walk():
            if isinstance(node, _WRITE_NODES):
                raise ReadOnlyViolation(f"{type(node).__name__} is not permitted inside a read statement")
            if isinstance(node, exp.Select) and node.args.get("locks"):
                raise ReadOnlyViolation("locking read is not permitted")
        verdict.objects = _objects_read(tree)
    else:
        verdict.parser = "tokenizer"
        verdict.kind = {"SEL": "select", "WITH": "select", "DESC": "describe"}.get(lead, lead.lower())
        if scope is not None:
            raise ReadOnlyViolation("statement could not be parsed, so the objects it reads cannot be verified")
    if scope is not None:
        check_scope(verdict.objects, scope)
    return verdict


def check_scope(objects: Iterable[str], scope: Iterable[str]) -> None:
    patterns = [p.lower() for p in scope]
    for obj in objects:
        name = obj.lower()
        if not any(fnmatch.fnmatchcase(name, p) for p in patterns):
            raise ReadOnlyViolation(
                f"'{obj}' is not in the permission manifest's objects_read (user data is never harvested)"
            )


# --------------------------------------------------------------------------- statement log


@dataclass
class LogEntry:
    seq: int
    at: datetime
    dialect: str
    sql: str
    verdict: str  # allowed | refused
    reason: str | None = None
    objects: list[str] = field(default_factory=list)
    rows: int | None = None


class StatementLog:
    """Every statement presented to a read-only connection, in order."""

    def __init__(self) -> None:
        self.entries: list[LogEntry] = []

    def add(self, **kw: Any) -> LogEntry:
        entry = LogEntry(seq=len(self.entries) + 1, at=datetime.now(timezone.utc).replace(tzinfo=None), **kw)
        self.entries.append(entry)
        if entry.verdict == "refused":
            log.warning("refused statement #%d: %s", entry.seq, entry.reason)
        else:
            log.info("read statement #%d on %s", entry.seq, ", ".join(entry.objects) or "-")
        return entry

    def allowed(self) -> list[LogEntry]:
        return [e for e in self.entries if e.verdict == "allowed"]

    def refused(self) -> list[LogEntry]:
        return [e for e in self.entries if e.verdict == "refused"]

    def __len__(self) -> int:
        return len(self.entries)


# --------------------------------------------------------------------------- execution-time transpilation


def transpile_for(sql: str, read: str, write: str) -> str:
    """Render a vetted source-dialect statement for an emulated catalog (e.g. DuckDB fixtures)."""
    tree = sqlglot.parse_one(sql, read=read)
    for j in tree.find_all(exp.Join):
        lat = j.this
        if isinstance(lat, exp.Lateral) and lat.args.get("cross_apply") is not None:
            outer = lat.args.get("cross_apply") is False
            lat.set("cross_apply", None)
            j.set("kind", None if outer else "CROSS")
            if outer:
                j.set("side", "LEFT")
                j.set("on", exp.true())
    return tree.sql(dialect=write)


# --------------------------------------------------------------------------- connection / cursor


class ReadOnlyCursor:
    """DB-API cursor facade that only executes vetted read statements."""

    __slots__ = ("_conn", "_cur", "rowcount", "description")

    def __init__(self, conn: "ReadOnlyConnection"):
        self._conn = conn
        self._cur = None
        self.rowcount = -1
        self.description = None

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> "ReadOnlyCursor":
        to_run = self._conn._vet(sql)
        cur = self._conn._driver_cursor()
        if params:
            cur.execute(to_run, list(params))
        else:
            cur.execute(to_run)
        self._cur = cur
        self.description = cur.description
        self.rowcount = getattr(cur, "rowcount", -1)
        return self

    def fetchall(self) -> list[tuple]:
        rows = list(self._cur.fetchall()) if self._cur is not None else []
        self._conn._record_rows(len(rows))
        return rows

    def fetchone(self) -> tuple | None:
        return self._cur.fetchone() if self._cur is not None else None

    def fetchmany(self, size: int = 1) -> list[tuple]:
        return list(self._cur.fetchmany(size)) if self._cur is not None else []

    def executemany(self, *_: Any, **__: Any) -> None:
        self._conn._refuse("executemany is a write path and is not available on a read-only connection")

    def callproc(self, *_: Any, **__: Any) -> None:
        self._conn._refuse("callproc is not available on a read-only connection")

    def close(self) -> None:
        if self._cur is not None and hasattr(self._cur, "close"):
            self._cur.close()
        self._cur = None

    def __iter__(self):
        return iter(self.fetchall())


class ReadOnlyConnection:
    """Wraps any DB-API connection; only read statements ever reach the driver.

    ``dialect``          the source dialect statements are written and vetted in.
    ``scope``            fnmatch patterns of objects the connection may read
                         (the permission manifest's ``objects_read``); ``None``
                         disables the scope check (not used by harvesters).
    ``execute_dialect``  when set, vetted statements are transpiled to this
                         dialect before execution (DuckDB-emulated catalogs).
    """

    __slots__ = ("__raw", "dialect", "scope", "execute_dialect", "log", "_closed")

    def __init__(self, raw: Any, dialect: str, *, scope: Iterable[str] | None = None,
                 execute_dialect: str | None = None, log: StatementLog | None = None):
        if isinstance(raw, ReadOnlyConnection):
            raise TypeError("connection is already read-only wrapped")
        _sg_dialect(dialect)
        self.__raw = raw
        self.dialect = dialect.lower()
        self.scope = list(scope) if scope is not None else None
        self.execute_dialect = execute_dialect
        self.log = log or StatementLog()
        self._closed = False

    # -- vetting
    def _refuse(self, reason: str, sql: str = "") -> None:
        self.log.add(dialect=self.dialect, sql=sql, verdict="refused", reason=reason)
        raise ReadOnlyViolation(reason)

    def _vet(self, sql: str) -> str:
        if self._closed:
            raise ReadOnlyViolation("connection is closed")
        try:
            verdict = classify_statement(sql, self.dialect, self.scope)
        except ReadOnlyViolation as e:
            self.log.add(dialect=self.dialect, sql=str(sql), verdict="refused", reason=str(e))
            raise
        self.log.add(dialect=self.dialect, sql=sql, verdict="allowed", objects=verdict.objects)
        if self.execute_dialect:
            return transpile_for(sql, _sg_dialect(self.dialect), _sg_dialect(self.execute_dialect))
        return sql

    def _record_rows(self, n: int) -> None:
        if self.log.entries:
            self.log.entries[-1].rows = n

    def _driver_cursor(self) -> Any:
        return self.__raw.cursor()

    # -- DB-API surface (read-only)
    def cursor(self) -> ReadOnlyCursor:
        return ReadOnlyCursor(self)

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> ReadOnlyCursor:
        return self.cursor().execute(sql, params)

    def query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read statement and return rows as dicts keyed by lower-case column name."""
        cur = self.execute(sql)
        cols = [d[0].lower() for d in cur.description or []]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def commit(self) -> None:
        """No-op: nothing can have been written."""

    def rollback(self) -> None:
        """No-op: nothing can have been written."""

    def close(self) -> None:
        self._closed = True

    def __enter__(self) -> "ReadOnlyConnection":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(f"ReadOnlyConnection exposes no attribute {name!r} (no raw driver access)")


def read_only(raw: Any, dialect: str, **kw: Any) -> ReadOnlyConnection:
    """Wrap ``raw`` unless it is already a :class:`ReadOnlyConnection`."""
    if isinstance(raw, ReadOnlyConnection):
        return raw
    return ReadOnlyConnection(raw, dialect, **kw)
