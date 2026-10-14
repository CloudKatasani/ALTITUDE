"""Static reference extraction from source code (procedures, scripts, query text).

Procedural dialects (T-SQL, PL/SQL, SPL, BTEQ) are not fully parseable by any
single parser, so references are found with a comment/literal-aware scanner:
reads (FROM/JOIN/USING), writes (INSERT/UPDATE/DELETE/MERGE/TRUNCATE/SELECT
INTO, Teradata INS/UPD/DEL) and calls (EXEC/EXECUTE/CALL). Names inside string
literals (dynamic SQL) are deliberately invisible — that blind spot is itself
an assessment signal (MS-06).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_PART = r'(?:\[[^\]\n]+\]|"[^"\n]+"|[A-Za-z_#@$][\w$#@]*)'
_NAME = rf"{_PART}(?:\s*\.\s*{_PART}){{0,3}}"
_VERBS = (
    r"INSERT\s+INTO|INSERT|INS\s+INTO|INS|UPDATE|UPD|DELETE\s+FROM|DELETE|DEL\s+FROM|DEL|MERGE\s+INTO|MERGE"
    r"|TRUNCATE\s+TABLE|INTO|FROM|JOIN|USING|EXECUTE|EXEC|CALL"
)
_REF = re.compile(rf"\b(?P<verb>{_VERBS})\s+(?P<name>{_NAME})(?P<after>\s*\(?)", re.IGNORECASE)
_KIND = {
    "INSERT INTO": "writes", "INSERT": "writes", "INS INTO": "writes", "INS": "writes", "UPDATE": "writes",
    "UPD": "writes", "DELETE FROM": "writes", "DELETE": "writes", "DEL FROM": "writes", "DEL": "writes",
    "MERGE INTO": "writes", "MERGE": "writes", "TRUNCATE TABLE": "writes", "INTO": "writes",
    "FROM": "reads", "JOIN": "reads", "USING": "reads", "EXECUTE": "calls", "EXEC": "calls", "CALL": "calls",
}
_NOT_NAMES = {"select", "set", "values", "where", "table", "the", "with", "as", "on", "dual", "lateral",
              "unnest", "openjson", "table_name", "sql", "immediate", "sp_executesql", "inserted", "deleted",
              "current_date", "current_timestamp", "sysdate", "systimestamp"}


def blank_comments_and_strings(text: str) -> str:
    """Replace comments and string literals with spaces, preserving offsets and line numbers."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
        elif text[i] == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and text.startswith("''", j):
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out)


def normalize_name(name: str) -> str:
    parts = [p.strip().strip("[]\"`") for p in re.split(r"\s*\.\s*", name.strip())]
    return ".".join(p for p in parts if p).lower()


@dataclass
class CodeRefs:
    reads: set[str] = field(default_factory=set)
    writes: set[str] = field(default_factory=set)
    calls: set[str] = field(default_factory=set)

    def all(self) -> set[str]:
        return self.reads | self.writes | self.calls

    def by_kind(self) -> dict[str, set[str]]:
        return {"reads": self.reads, "writes": self.writes, "calls": self.calls}


def code_refs(text: str | None) -> CodeRefs:
    refs = CodeRefs()
    if not text:
        return refs
    clean = blank_comments_and_strings(text)
    for m in _REF.finditer(clean):
        verb = re.sub(r"\s+", " ", m.group("verb").upper())
        name = normalize_name(m.group("name"))
        kind = _KIND[verb]
        if not name or name in _NOT_NAMES or name.startswith(("@", "#")) or name.split(".")[-1].startswith("#"):
            continue
        if kind == "calls" and m.group("after").strip() == "(":
            continue  # EXEC('...') / EXEC (@sql): dynamic SQL, not a named call
        if kind == "writes" and verb == "INTO" and name.startswith(("v_", "l_", "p_")):
            continue  # PL/SQL SELECT ... INTO variable
        getattr(refs, kind).add(name)
    return refs


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1
