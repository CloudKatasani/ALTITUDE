"""Teradata static detectors (BTEQ/SPL aware: dot-commands never reach the SQL parser)."""

from __future__ import annotations

import re
from typing import Iterable

from sqlglot import exp

from ..model import Finding
from ..source import SourceContext, type_family
from . import hit, static

_NAME = r"[\w.\"$#]+"
_TBL_KIND = r"(?:(?:GLOBAL\s+TEMPORARY|VOLATILE)\s+)?"


@static("td_set_table", "Teradata SET tables (explicit, or implicit in Teradata session mode) and inserts into them")
def td_set_table(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Teradata SET tables reject exact duplicate rows silently; Snowflake tables keep every row, so "
                 "loads that relied on SET semantics now produce duplicates.")
    set_tables: set[str] = set()
    for m in ctx.find(rf"\bCREATE\s+{_TBL_KIND}SET\s+{_TBL_KIND}TABLE\s+({_NAME})"):
        set_tables.add(m.m.group(1).lower().split(".")[-1].strip('"'))
        yield hit(m, "strong", f"SET table {m.m.group(1)}", rationale)
    for m in ctx.find(rf"\bCREATE\s+{_TBL_KIND}TABLE\s+({_NAME})"):
        yield hit(m, "weak", f"CREATE TABLE {m.m.group(1)} without MULTISET (SET by default in Teradata mode)",
                  rationale + " Without MULTISET the table is SET when the session runs in Teradata (BTET) mode.")
    if set_tables:
        for m in ctx.find(rf"\bINSERT\s+INTO\s+({_NAME})"):
            if m.m.group(1).lower().split(".")[-1].strip('"') in set_tables:
                yield hit(m, "strong", f"INSERT into SET table {m.m.group(1)}", rationale)


@static("td_case_insensitive", "NOT CASESPECIFIC columns, BTET sessions and predicates on such columns")
def td_case_insensitive(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Teradata compares NOT CASESPECIFIC columns (the default in Teradata session mode) "
                 "case-insensitively; Snowflake compares case-sensitively unless a collation is declared.")
    for m in ctx.find(r"\bNOT\s+CASESPECIFIC\b|\(\s*NOT\s+CS\s*\)|\bNOT\s+CS\b"):
        yield hit(m, "strong", "NOT CASESPECIFIC column attribute", rationale)
    for m in ctx.find(r"^\s*\.?SET\s+SESSION\s+TRANSACTION\s+BTET\b", flags=re.IGNORECASE | re.MULTILINE):
        yield hit(m, "medium", "Teradata (BTET) session mode: character columns default to NOT CASESPECIFIC",
                  rationale)
    ci_cols = {c for c, t in ctx.ddl_columns.items() if re.search(r"\bNOT\s+(CASESPECIFIC|CS)\b", t)}
    if not ci_cols:
        return
    for st in ctx.statements:
        if not st.parsed:
            continue
        for node in st.ast.find_all(exp.EQ, exp.NEQ, exp.In, exp.Like, exp.GT, exp.LT, exp.GTE, exp.LTE):
            cols = [c for c in node.find_all(exp.Column) if c.name.lower() in ci_cols]
            if cols:
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"predicate on NOT CASESPECIFIC column {cols[0].name}",
                              "strong", rationale)


@static("td_char_columns", "CHAR(n) columns, especially when used in joins or equality predicates")
def td_char_columns(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Teradata compares CHAR values with pad semantics (trailing spaces ignored). Exported CHAR "
                 "values keep their padding and Snowflake compares them exactly, so joins to VARCHAR keys fail.")
    for m in ctx.find(r"\b(\w+)\s+CHAR(ACTER)?\s*\(\s*\d+\s*\)(?!\s*VARYING)"):
        yield hit(m, "medium", f"CHAR column {m.m.group(1)}", rationale)
    char_cols = {c for c, t in ctx.ddl_columns.items() if re.match(r"^CHAR(ACTER)?\s*\(", t)}
    if not char_cols:
        return
    for st in ctx.statements:
        if not st.parsed:
            continue
        for node in st.ast.find_all(exp.EQ, exp.NEQ, exp.In):
            cols = [c for c in node.find_all(exp.Column) if c.name.lower() in char_cols]
            if cols:
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"comparison/join on CHAR column {cols[0].name}", "strong",
                              rationale)


_CYYMMDD = r"\b1?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\b"


@static("td_integer_date", "Integer-encoded dates (CYYMMDD), int<->date casts and FORMAT clauses")
def td_integer_date(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Teradata stores DATE as the integer (year-1900)*10000 + month*100 + day and converts implicitly; "
                 "Snowflake has no such encoding (integer strings are read as epoch seconds), so values shift or fail.")
    for st in ctx.statements:
        if not st.parsed:
            continue
        for cast in st.ast.find_all(exp.Cast):
            to = cast.args.get("to")
            if not isinstance(to, exp.DataType) or not isinstance(cast.this, exp.Column):
                continue
            fam = type_family(ctx.column_type(cast.this.name))
            if to.is_type(exp.DataType.Type.DATE) and fam == "integer":
                line = ctx.node_line(st, cast)
                yield Finding(line, ctx.line_text(line), f"CAST of integer column {cast.this.name} to DATE",
                              "strong", rationale)
            elif to.is_type(*exp.DataType.INTEGER_TYPES) and fam == "date":
                line = ctx.node_line(st, cast)
                yield Finding(line, ctx.line_text(line), f"CAST of DATE column {cast.this.name} to INTEGER",
                              "strong", rationale)
        for cmp in st.ast.find_all(exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between):
            cols = [c for c in cmp.find_all(exp.Column) if type_family(ctx.column_type(c.name)) == "date"]
            lits = [lit for lit in cmp.find_all(exp.Literal) if lit.is_int and re.fullmatch(_CYYMMDD, lit.this)]
            if cols and lits:
                line = ctx.node_line(st, cmp)
                yield Finding(line, ctx.line_text(line), f"DATE column {cols[0].name} compared to integer date "
                              f"{lits[0].this}", "strong", rationale)
    for m in ctx.find(rf"{_CYYMMDD}\s*\(\s*DATE\b"):
        yield hit(m, "strong", "integer literal cast with (DATE)", rationale)
    for m in ctx.find(r"\(\s*FORMAT\s+'[^']*'\s*\)|\bFORMAT\s+'[YMD/\-]+'", view="code"):
        yield hit(m, "medium", "Teradata FORMAT clause on a date", rationale)


@static("td_bteq_control", "BTEQ dot-command control flow and error handling")
def td_bteq_control(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("BTEQ control flow (.IF ERRORCODE/.ACTIVITYCOUNT, .GOTO/.LABEL, .QUIT) has no SQL equivalent; it "
                 "must be rebuilt with Snowflake Scripting exceptions/SQLROWCOUNT and an orchestrator.")
    rx = re.compile(r"^[ \t]*\.(IF|GOTO|LABEL|QUIT|EXIT|ERRORLEVEL|MAXERROR|ERROROUT|OS|RUN)\b",
                    re.IGNORECASE | re.MULTILINE)
    for m in ctx.find(rx):
        yield hit(m, "strong", f"BTEQ .{m.m.group(1).upper()} command", rationale)
    for m in ctx.find(r"\b(ACTIVITYCOUNT|ERRORCODE)\b"):
        yield hit(m, "strong", f"BTEQ {m.m.group(1).upper()} status variable", rationale)


@static("td_timestamp_tz", "Session time zone, TIMESTAMP WITH TIME ZONE and timestamp-to-date casts")
def td_timestamp_tz(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Teradata evaluates timestamps in the session/DBS time zone; Snowflake uses TIMESTAMP_TYPE_MAPPING "
                 "and the account TIMEZONE, so day boundaries and precision change unless the policy is explicit.")
    for m in ctx.find(r"\bSET\s+TIME\s+ZONE\b"):
        yield hit(m, "strong", "session time zone set in script", rationale)
    for m in ctx.find(r"\bAT\s+(LOCAL|TIME\s+ZONE)\b"):
        yield hit(m, "medium", "AT LOCAL / AT TIME ZONE conversion", rationale)
    for m in ctx.find(r"\bTIMESTAMP\s*\(\s*\d\s*\)\s+WITH\s+TIME\s+ZONE\b|\bTIME\s*\(\s*\d\s*\)\s+WITH\s+TIME\s+ZONE\b"):
        yield hit(m, "medium", "TIMESTAMP WITH TIME ZONE column", rationale)
    ts_cols = {c for c, t in ctx.ddl_columns.items() if type_family(t) == "timestamp"}
    for st in ctx.statements:
        if not st.parsed or not ts_cols:
            continue
        for cast in st.ast.find_all(exp.Cast):
            to = cast.args.get("to")
            if (isinstance(to, exp.DataType) and to.is_type(exp.DataType.Type.DATE)
                    and isinstance(cast.this, exp.Column) and cast.this.name.lower() in ts_cols):
                line = ctx.node_line(st, cast)
                yield Finding(line, ctx.line_text(line), f"day boundary from timestamp column {cast.this.name}",
                              "medium", rationale)
