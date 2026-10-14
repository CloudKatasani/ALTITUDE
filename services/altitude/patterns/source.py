"""Source-code context for static detectors.

Source scripts mix SQL with things a SQL parser does not understand (BTEQ dot-commands,
T-SQL batches and control flow, PL/SQL blocks, shell). :class:`SourceContext` therefore
offers two complementary views with identical character offsets:

- ``code``   comments blanked, string literals kept (for literal-sensitive rules);
- ``nostr``  comments *and* string-literal contents blanked (for keyword rules), so
  text inside comments or strings never triggers a detector;

plus best-effort per-statement sqlglot ASTs (dialect-aware) with line mapping. Detectors
use the AST where a statement parses and fall back to robust regex/token rules where it
does not.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Iterator

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, TokenError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

SQLGLOT_DIALECT = {
    "teradata": "teradata",
    "oracle": "oracle",
    "sqlserver": "tsql",
    "netezza": "postgres",
    "redshift": "redshift",
}

_GO_LINE = re.compile(r"^[ \t]*GO[ \t]*$", re.IGNORECASE | re.MULTILINE)
_DOT_LINE = re.compile(r"^[ \t]*\.[A-Za-z]", re.MULTILINE)


def mask(sql: str, strings: bool) -> str:
    """Blank comments (and string-literal contents when ``strings``) keeping offsets and newlines."""
    out = list(sql)
    n = len(sql)
    i = 0

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = sql[i]
        if c == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            j = n if j == -1 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and sql.startswith("/*", i):
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            blank(i, j)
            i = j
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if sql[j] == "'":
                    if j + 1 < n and sql[j + 1] == "'":
                        j += 2
                        continue
                    break
                j += 1
            if strings:
                blank(i + 1, j)
            i = j + 1
            continue
        if c == '"':
            j = sql.find('"', i + 1)
            i = n if j == -1 else j + 1
            continue
        i += 1
    return "".join(out)


@dataclass
class Statement:
    text: str            # comment-masked statement text (offsets preserved)
    start: int           # character offset in the script
    start_line: int      # 1-based line of ``start``
    ast: exp.Expression | None
    error: str | None

    @property
    def parsed(self) -> bool:
        return self.ast is not None and not isinstance(self.ast, exp.Command)


@dataclass
class Match:
    line: int
    snippet: str
    m: re.Match


class SourceContext:
    def __init__(self, sql: str, dialect: str):
        self.sql = sql.replace("\r\n", "\n")
        self.dialect = dialect
        self.code = mask(self.sql, strings=False)
        self.nostr = mask(self.sql, strings=True)
        self.lines = self.sql.split("\n")
        self._line_starts = [0]
        for idx, ch in enumerate(self.sql):
            if ch == "\n":
                self._line_starts.append(idx + 1)

    # ------------------------------------------------------------------ positions
    def line_of(self, offset: int) -> int:
        lo, hi = 0, len(self._line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    def line_text(self, line: int) -> str:
        if 1 <= line <= len(self.lines):
            return self.lines[line - 1].strip()
        return ""

    # ------------------------------------------------------------------ regex
    def find(self, pattern: str | re.Pattern, view: str = "nostr", flags: int = re.IGNORECASE) -> Iterator[Match]:
        rx = pattern if isinstance(pattern, re.Pattern) else re.compile(pattern, flags)
        text = self.nostr if view == "nostr" else self.code
        for m in rx.finditer(text):
            line = self.line_of(m.start())
            yield Match(line, self.line_text(line), m)

    def find_in(self, stmt: Statement, pattern: str, flags: int = re.IGNORECASE,
                view: str = "nostr") -> Iterator[Match]:
        """Regex over one statement (``nostr`` view by default; ``code`` keeps string literals)."""
        rx = re.compile(pattern, flags)
        seg = (self.nostr if view == "nostr" else self.code)[stmt.start:stmt.start + len(stmt.text)]
        for m in rx.finditer(seg):
            line = self.line_of(stmt.start + m.start())
            yield Match(line, self.line_text(line), m)

    # ------------------------------------------------------------------ statements
    @cached_property
    def statements(self) -> list[Statement]:
        """Split on ``;``, T-SQL ``GO`` and BTEQ dot-command lines; parse each with sqlglot."""
        cuts: set[int] = set()
        for i, ch in enumerate(self.nostr):
            if ch == ";":
                cuts.add(i + 1)
        for m in _GO_LINE.finditer(self.nostr):
            cuts.update({m.start(), m.end()})
        if self.dialect == "teradata":
            for m in _DOT_LINE.finditer(self.nostr):
                end = self.nostr.find("\n", m.start())
                cuts.update({m.start(), len(self.nostr) if end == -1 else end})
        bounds = sorted(cuts | {0, len(self.sql)})
        out: list[Statement] = []
        read = SQLGLOT_DIALECT.get(self.dialect)
        for a, b in zip(bounds, bounds[1:]):
            raw = self.code[a:b]
            body = raw.strip().rstrip(";").strip()
            if not body:
                continue
            lead = len(raw) - len(raw.lstrip())
            start = a + lead
            text = self.code[start:b]
            ast, err = None, None
            if body.startswith(".") or _GO_LINE.fullmatch(body) or body.upper() == "GO":
                err = "dot-command"
            else:
                ast, err = _parse(text, read)
                if ast is None or isinstance(ast, exp.Command):
                    # Statement recovery: procedural wrappers (CREATE PROCEDURE ... BEGIN, BEGIN TRY, IS BEGIN)
                    # do not parse, but the DML inside them usually does.
                    m = _DML.search(self.nostr, start + 1, b)
                    if m:
                        rec_ast, _ = _parse(self.code[m.start():b], read)
                        if rec_ast is not None and not isinstance(rec_ast, exp.Command):
                            out.append(Statement(text=self.code[start:m.start()], start=start,
                                                 start_line=self.line_of(start), ast=None, error=err or "command"))
                            start, text, ast, err = m.start(), self.code[m.start():b], rec_ast, None
            out.append(Statement(text=text, start=start, start_line=self.line_of(start), ast=ast, error=err))
        return out

    def node_line(self, stmt: Statement, node: exp.Expression) -> int:
        """Best line for an AST node: its own token position, else its first positioned descendant."""
        for n in node.walk():
            meta = n._meta if getattr(n, "_meta", None) else {}
            if "line" in meta:
                return stmt.start_line + int(meta["line"]) - 1
        return stmt.start_line

    # ------------------------------------------------------------------ DDL catalogue
    @cached_property
    def ddl_columns(self) -> dict[str, str]:
        """``{column_name_lower: TYPE TEXT UPPER}`` from CREATE TABLE bodies and DECLAREd variables.

        Regex-based so it works for Teradata SET/MULTISET, T-SQL and PL/SQL DDL alike. Table
        qualification is ignored (a script-level approximation).
        """
        cols: dict[str, str] = {}
        for m in re.finditer(r"\bCREATE\b[^;(]*?\bTABLE\b\s+[\w.\"\[\]$#]+([^;(]*)\(", self.nostr, re.IGNORECASE):
            if re.search(r"\bAS\b", m.group(1), re.IGNORECASE):
                continue
            body = _paren_body(self.nostr, m.end() - 1)
            for item in _split_top_level(body):
                tok = item.strip().split(None, 1)
                if len(tok) != 2:  # threshold-ok: "name type" token pair
                    continue
                name = tok[0].strip('"[]').lower()
                if name in {"primary", "constraint", "unique", "foreign", "check", "index", "period"}:
                    continue
                cols[name] = " ".join(tok[1].split()).upper()
        for m in re.finditer(r"\bDECLARE\s+(@\w+)\s+([A-Za-z_][\w]*(?:\s*\([^)]*\))?)", self.nostr, re.IGNORECASE):
            cols[m.group(1).lower()] = m.group(2).upper()
        return cols

    def column_type(self, name: str) -> str | None:
        return self.ddl_columns.get(name.strip('"[]').lower())


_DML = re.compile(r"\b(SELECT|INSERT|UPDATE|DELETE|MERGE|WITH)\b", re.IGNORECASE)


def _parse(text: str, read: str | None) -> tuple[exp.Expression | None, str | None]:
    try:
        parsed = sqlglot.parse(text, read=read, error_level=ErrorLevel.RAISE)
        return next((p for p in parsed if p is not None), None), None
    except (ParseError, TokenError, ValueError, RecursionError) as e:
        return None, (str(e).splitlines()[0][:200] if str(e) else type(e).__name__)


def _paren_body(text: str, open_idx: int) -> str:
    depth = 0
    for i in range(open_idx, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
    return text[open_idx + 1:]


def _split_top_level(body: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in body:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return parts


# --------------------------------------------------------------------------- type helpers

_INT_TYPES = re.compile(r"^(BYTEINT|SMALLINT|INTEGER|INT|BIGINT|TINYINT|INT[248])\b")
_NUMBER_P = re.compile(r"^(NUMBER|NUMERIC|DECIMAL|DEC)\s*\(\s*(\d+|\*)\s*(?:,\s*(-?\d+)\s*)?\)")
_STRING_TYPES = re.compile(r"^(N?VARCHAR2?|N?CHAR(ACTER)?|VARCHAR|TEXT|STRING|CLOB|NVARCHAR|NCHAR)\b")
_FLOAT_TYPES = re.compile(r"^(FLOAT|REAL|DOUBLE|BINARY_DOUBLE|BINARY_FLOAT)\b")


def type_family(type_text: str | None) -> str | None:
    """Family of a DDL type text: integer | decimal | float | string | date | timestamp | None."""
    if not type_text:
        return None
    t = type_text.upper().strip()
    if _INT_TYPES.match(t):
        return "integer"
    m = _NUMBER_P.match(t)
    if m:
        scale = m.group(3)
        return "integer" if (scale is None or int(scale) == 0) and m.group(2) != "*" else "decimal"
    if re.match(r"^(NUMBER|NUMERIC|DECIMAL|MONEY|SMALLMONEY)\b", t):
        return "decimal"
    if _FLOAT_TYPES.match(t):
        return "float"
    if _STRING_TYPES.match(t):
        return "string"
    if re.match(r"^(TIMESTAMP|DATETIME|SMALLDATETIME|DATETIME2|DATETIMEOFFSET)", t):
        return "timestamp"
    if re.match(r"^DATE\b", t):
        return "date"
    return None
