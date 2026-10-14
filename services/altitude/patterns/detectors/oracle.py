"""Oracle / PL/SQL static detectors."""

from __future__ import annotations

import re
from typing import Iterable

from sqlglot import exp

from ..model import Finding
from ..source import SourceContext, type_family
from . import hit, static


def _string_or_unknown(ctx: SourceContext, node: exp.Expression) -> str | None:
    """'string' | 'unknown' when ``node`` may be a character value, else None."""
    if isinstance(node, exp.Column):
        fam = type_family(ctx.column_type(node.name))
        if fam == "string":
            return "string"
        return "unknown" if fam is None else None
    if isinstance(node, exp.Literal) and node.is_string:
        return None
    return None


@static("or_empty_string_null", "NULL tests, NVL/COALESCE, '' comparisons and || concatenation on character data")
def or_empty_string_null(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Oracle stores '' as NULL; Snowflake keeps '' distinct from NULL, so IS NULL filters, NVL/COALESCE "
                 "defaults, COUNT(col) and || concatenation behave differently on migrated data.")
    for m in ctx.find(r"(=|<>|!=)\s*''(?!')", view="code"):
        yield hit(m, "strong", "comparison with '' (never true in Oracle)", rationale)
    for st in ctx.statements:
        if st.parsed:
            for node in st.ast.find_all(exp.Is):
                if isinstance(node.expression, exp.Null):
                    kind = _string_or_unknown(ctx, node.this)
                    if kind:
                        line = ctx.node_line(st, node)
                        yield Finding(line, ctx.line_text(line), f"IS NULL test on {node.this.sql()}",
                                      "strong" if kind == "string" else "medium", rationale)
            for node in st.ast.find_all(exp.Coalesce):
                kind = _string_or_unknown(ctx, node.this)
                if kind:
                    line = ctx.node_line(st, node)
                    yield Finding(line, ctx.line_text(line), f"NVL/COALESCE default on {node.this.sql()}",
                                  "strong" if kind == "string" else "medium", rationale)
            for node in st.ast.find_all(exp.DPipe):
                if isinstance(node.parent, exp.DPipe):
                    continue
                cols = [c for c in node.find_all(exp.Column) if _string_or_unknown(ctx, c)
                        and not isinstance(c.parent, exp.Coalesce)]
                if cols:
                    line = ctx.node_line(st, node)
                    yield Finding(line, ctx.line_text(line), f"|| concatenation with nullable {cols[0].name}",
                                  "medium", rationale)
        elif st.error != "dot-command":
            for m in ctx.find_in(st, r"\bIS\s+(NOT\s+)?NULL\b|\bNVL2?\s*\("):
                yield hit(m, "medium", "NULL handling (token rule; statement did not parse)", rationale)


@static("or_unscaled_number", "NUMBER without precision/scale")
def or_unscaled_number(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Oracle NUMBER without precision stores any scale; mapped to Snowflake NUMBER it becomes "
                 "NUMBER(38,0) and silently rounds decimals.")
    for m in ctx.find(r"\bNUMBER\b(?!\s*\()|\bNUMBER\s*\(\s*\*\s*\)"):
        yield hit(m, "strong", "unscaled NUMBER", rationale)


@static("or_date_type", "Oracle DATE columns and time-of-day usage")
def or_date_type(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = "Oracle DATE includes the time of day; mapping it to Snowflake DATE drops the time component."
    for col, t in ctx.ddl_columns.items():
        if type_family(t) == "date":
            for m in ctx.find(rf"\b{re.escape(col)}\s+DATE\b"):
                yield hit(m, "medium", f"DATE column {col}", rationale)
    for m in ctx.find(r"\bTO_DATE\s*\([^)]*'[^']*\b(HH24|HH12|HH|MI|SS)\b[^']*'", view="code"):
        yield hit(m, "strong", "TO_DATE with a time-of-day format", rationale)
    for m in ctx.find(r"\bSYSDATE\b"):
        yield hit(m, "medium", "SYSDATE (DATE with time of day)", rationale)
    for m in ctx.find(r"\bTRUNC\s*\(\s*[\w.]+\s*\)"):
        yield hit(m, "weak", "TRUNC(date) relies on DATE carrying time", rationale)


@static("or_package_state", "PL/SQL packages and autonomous transactions")
def or_package_state(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Snowflake has no packages: package-level state, overloading and autonomous transactions must "
                 "be redesigned (state tables/session variables, separate logging).")
    for m in ctx.find(r"\bCREATE\s+(OR\s+REPLACE\s+)?PACKAGE(\s+BODY)?\b"):
        yield hit(m, "strong", "PL/SQL package", rationale)
    for m in ctx.find(r"\bPRAGMA\s+AUTONOMOUS_TRANSACTION\b"):
        yield hit(m, "strong", "autonomous transaction", rationale)


@static("or_outer_join_plus", "Legacy (+) outer-join operator")
def or_outer_join_plus(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\(\s*\+\s*\)"):
        yield hit(m, "strong", "(+) outer join",
                  "Legacy (+) joins must become ANSI outer joins; misplaced filters turn them into inner joins.")


@static("or_nls", "NLS session settings and format-less TO_CHAR/TO_DATE")
def or_nls(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Without an explicit format model Oracle uses NLS_DATE_FORMAT/NLS_SORT/NLS_COMP; Snowflake uses "
                 "its own session parameters, so rendered dates, parsing and sort order change.")
    for m in ctx.find(r"\bALTER\s+SESSION\s+SET\s+NLS_\w+"):
        yield hit(m, "strong", "NLS session setting", rationale)
    for m in ctx.find(r"\bTO_DATE\s*\(\s*'[^']*'\s*\)", view="code"):
        yield hit(m, "strong", "TO_DATE literal without format model", rationale)
    for m in ctx.find(r"\bTO_(CHAR|DATE)\s*\(\s*[\w.:]+\s*\)", view="code"):
        yield hit(m, "medium", f"TO_{m.m.group(1).upper()} without format model", rationale)


@static("or_lob_types", "LONG, LOB, XMLTYPE and spatial types")
def or_lob_types(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\b\w+\s+(LONG\s+RAW|LONG|N?CLOB|BLOB|BFILE|XMLTYPE|SDO_GEOMETRY)\b"):
        yield hit(m, "medium", f"{m.m.group(1).upper()} column",
                  "Check current Snowflake size limits; use VARIANT/GEOGRAPHY or externalise large binaries.")


@static("or_exadata_storage", "Exadata HCC compression and parallel-degree clauses")
def or_exadata_storage(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = "Exadata smart scan/HCC performance has no 1:1 equivalent; measure before designing clustering."
    for m in ctx.find(r"\bCOMPRESS\s+FOR\s+(QUERY|ARCHIVE)\b"):
        yield hit(m, "medium", "Hybrid Columnar Compression", rationale)
    for m in ctx.find(r"\bPARALLEL\s+\d+\b"):
        yield hit(m, "weak", "parallel degree clause", rationale)
