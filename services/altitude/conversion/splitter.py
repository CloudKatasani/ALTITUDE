"""Dialect-aware SQL script splitter.

Splits a script into statement units, keeping each unit's exact text and line span so issues and
remediations can be located precisely. Handles comments, quoted strings/identifiers, ``$$`` bodies,
BEGIN/CASE ... END nesting, BTEQ dot-commands (Teradata), ``/`` terminators (Oracle PL/SQL) and
``GO`` batch separators (T-SQL).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEADING_NOISE = re.compile(r"^(?:\s+|--[^\n]*(?:\n|$)|/\*.*?\*/)*", re.S)
_BLOCK_HEADERS = {
    "oracle": re.compile(
        r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?(?:(?:NON)?EDITIONABLE\s+)?(?:PACKAGE|PROCEDURE|FUNCTION|TRIGGER|TYPE\s+BODY)\b"
        r"|DECLARE\b|BEGIN\b)",
        re.I,
    ),
    "tsql": re.compile(r"^CREATE\s+(?:OR\s+ALTER\s+)?(?:PROC|PROCEDURE|FUNCTION|TRIGGER)\b", re.I),
}
_NO_DEPTH_AFTER_BEGIN = {"TRAN", "TRANSACTION", "WORK", "DISTRIBUTED"}
_NO_DEPTH_AFTER_END = {"IF", "LOOP", "WHILE", "FOR", "REPEAT"}


@dataclass
class Unit:
    text: str
    start_line: int
    end_line: int
    kind: str  # sql|dot|comment

    @property
    def code(self) -> str:
        """Text without leading comments/whitespace."""
        return _LEADING_NOISE.sub("", self.text, count=1)


def _line_of(text: str, idx: int) -> int:
    return text.count("\n", 0, idx) + 1


def _make_unit(text: str, start: int, end: int, kind: str | None = None) -> Unit | None:
    chunk = text[start:end]
    if not chunk.strip():
        return None
    first = start + (len(chunk) - len(chunk.lstrip()))
    last = start + len(chunk.rstrip()) - 1
    code = _LEADING_NOISE.sub("", chunk, count=1)
    k = kind or ("sql" if code.strip() else "comment")
    return Unit(chunk, _line_of(text, first), _line_of(text, last), k)


def split_statements(text: str, dialect: str = "snowflake") -> list[Unit]:
    units: list[Unit] = []
    n = len(text)
    i = 0
    buf_start = 0
    depth = 0
    block_re = _BLOCK_HEADERS.get(dialect)

    def emit(end: int, kind: str | None = None) -> None:
        u = _make_unit(text, buf_start, end, kind)
        if u:
            units.append(u)

    def buffer_has_code(upto: int) -> bool:
        return bool(_LEADING_NOISE.sub("", text[buf_start:upto], count=1).strip())

    def next_word(pos: int) -> str:
        m = re.compile(r"\s*([A-Za-z_]+)").match(text, pos)
        return m.group(1).upper() if m else ""

    while i < n:
        at_line_start = i == 0 or text[i - 1] == "\n"
        if at_line_start:
            eol = text.find("\n", i)
            eol = n if eol == -1 else eol
            line = text[i:eol]
            stripped = line.strip()
            is_sep = stripped == "/" or (dialect == "tsql" and stripped.upper() == "GO")
            if is_sep:
                emit(i)
                buf_start = min(eol + 1, n)
                depth = 0
                i = buf_start
                continue
            if dialect == "teradata" and stripped.startswith(".") and not buffer_has_code(i):
                emit(i)  # flush pending comments as their own unit
                buf_start = i
                emit(eol, "dot")
                buf_start = min(eol + 1, n)
                i = buf_start
                continue
        c = text[i]
        two = text[i:i + 2]
        if two == "--":
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if two == "/*":
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
            continue
        if two == "$$":
            j = text.find("$$", i + 2)
            i = n if j == -1 else j + 2
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            i = j + 1
            continue
        if c == '"' or (c == "[" and dialect == "tsql"):
            close = '"' if c == '"' else "]"
            j = text.find(close, i + 1)
            i = n if j == -1 else j + 1
            continue
        if c.isalpha() or c == "_":
            m = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*").match(text, i)
            word = m.group(0).upper()
            prev = text[i - 1] if i else " "
            if prev not in ".@#$":
                if word == "BEGIN" and next_word(m.end()) not in _NO_DEPTH_AFTER_BEGIN:
                    depth += 1
                elif word == "CASE":
                    depth += 1
                elif word == "END" and next_word(m.end()) not in _NO_DEPTH_AFTER_END:
                    depth = max(0, depth - 1)
            i = m.end()
            continue
        if c == ";" and depth == 0:
            header = _LEADING_NOISE.sub("", text[buf_start:i], count=1)
            if block_re is not None and block_re.match(header):
                i += 1  # PL/SQL / T-SQL module: ends at '/' or GO (or EOF)
                continue
            emit(i + 1)
            buf_start = i + 1
            i += 1
            continue
        i += 1
    emit(n)
    return units


def statement_span(units: list[Unit], line: int) -> tuple[int, int] | None:
    """Return the (start_line, end_line) of the unit containing ``line``."""
    for u in units:
        if u.start_line <= line <= u.end_line:
            return u.start_line, u.end_line
    return None
