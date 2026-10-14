"""Static detectors shared by several dialects (AST-first, regex fallback)."""

from __future__ import annotations

import re
from typing import Iterable

from sqlglot import exp

from ..model import Finding
from ..source import SourceContext, type_family
from . import hit, static

_TRUNCATING = {"FLOOR", "CEIL", "CEILING", "ROUND", "TRUNC", "TRUNCATE"}


def _func_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.this).upper()
    return type(node).__name__.upper()


def int_kind(node: exp.Expression, ctx: SourceContext) -> str:
    """'int' | 'nonint' | 'unknown' for an arithmetic operand."""
    if isinstance(node, exp.Paren):
        return int_kind(node.this, ctx)
    if isinstance(node, exp.Literal):
        if node.is_string:
            return "nonint"
        return "int" if node.is_int else "nonint"
    if isinstance(node, exp.Count):
        return "int"
    if isinstance(node, (exp.Sum, exp.Min, exp.Max)):
        return int_kind(node.this, ctx)
    if isinstance(node, (exp.Cast, exp.TryCast)):
        to = node.args.get("to")
        if isinstance(to, exp.DataType):
            if to.is_type(*exp.DataType.INTEGER_TYPES):
                return "int"
            return "nonint"
        return "unknown"
    if isinstance(node, exp.Column):
        fam = type_family(ctx.column_type(node.name))
        if fam == "integer":
            return "int"
        if fam is None:
            return "unknown"
        return "nonint"
    if isinstance(node, (exp.Add, exp.Sub, exp.Mul, exp.Mod, exp.Div)):
        kinds = {int_kind(node.left, ctx), int_kind(node.right, ctx)}
        if "nonint" in kinds:
            return "nonint"
        return "int" if kinds == {"int"} else "unknown"
    if isinstance(node, exp.Avg):
        return "nonint"
    return "unknown"


def _explicitly_truncated(node: exp.Expression) -> bool:
    parent = node.parent
    while isinstance(parent, exp.Paren):
        parent = parent.parent
    if parent is None:
        return False
    if _func_name(parent) in _TRUNCATING:
        return True
    if isinstance(parent, (exp.Cast, exp.TryCast)) and isinstance(parent.args.get("to"), exp.DataType):
        return parent.args["to"].is_type(*exp.DataType.INTEGER_TYPES)
    return False


@static("int_division", "Integer / integer expressions (truncating in Teradata/Netezza, decimal in Snowflake)")
def int_division(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Both operands are integer-typed (literals, COUNT, INTEGER columns from the script's DDL); the "
                 "source engine truncates the quotient while Snowflake returns NUMBER with decimals.")
    for st in ctx.statements:
        if st.parsed:
            for div in st.ast.find_all(exp.Div):
                if _explicitly_truncated(div):
                    continue
                left, right = int_kind(div.left, ctx), int_kind(div.right, ctx)
                if {left, right} == {"int"}:
                    strength = "strong"
                elif "nonint" not in (left, right) and "int" in (left, right):
                    strength = "weak"
                else:
                    continue
                line = ctx.node_line(st, div)
                yield Finding(line, ctx.line_text(line), f"integer division `{div.sql(dialect='snowflake')}`",
                              strength, rationale if strength == "strong" else
                              "One operand is integer-typed and the other's type is unknown from the script; "
                              "verify the operand types before conversion.")
        elif st.error != "dot-command":
            for m in ctx.find_in(st, r"(\bCOUNT\s*\(\s*\*?\s*[\w.]*\s*\)|\b\d+)\s*/\s*(\d+\b|COUNT\s*\()"):
                yield hit(m, "medium", "integer division (token rule; statement did not parse)", rationale)


@static("update_from_join", "UPDATE ... FROM joins and MERGE whose source may match a target row more than once")
def update_from_join(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("An UPDATE driven by a join (or a MERGE) is deterministic only when the source has at most one row "
                 "per target key. Snowflake picks an arbitrary match (or errors with "
                 "ERROR_ON_NONDETERMINISTIC_UPDATE/MERGE), so a non-unique source silently changes results.")
    for st in ctx.statements:
        if st.parsed and isinstance(st.ast, exp.Update):
            if any(k.startswith("from") and v is not None for k, v in st.ast.args.items()) or st.ast.find(exp.Join):
                line = st.start_line
                yield Finding(line, ctx.line_text(line), "UPDATE with a joined source (UPDATE ... FROM)", "medium",
                              rationale)
        elif st.parsed and isinstance(st.ast, exp.Merge):
            line = st.start_line
            yield Finding(line, ctx.line_text(line), "MERGE; verify the source is unique on the ON key", "weak",
                          rationale)
        elif not st.parsed:
            for m in ctx.find_in(st, r"\bUPDATE\s+[\w.\"]+(\s+(AS\s+)?\w+)?\s+FROM\b"):
                yield hit(m, "medium", "Teradata-style UPDATE <t> FROM <t>, <s>", rationale)
            if not re.search(r"\bUPDATE\s+[\w.\"]+(\s+(AS\s+)?\w+)?\s+FROM\b", st.text, re.IGNORECASE):
                for m in ctx.find_in(st, r"\bUPDATE\b[\s\S]*?\bSET\b[\s\S]*?\bFROM\b"):
                    yield hit(m, "medium", "UPDATE ... SET ... FROM join (token rule)", rationale)
            for m in ctx.find_in(st, r"\bMERGE\s+INTO\b"):
                yield hit(m, "weak", "MERGE; verify the source is unique on the ON key", rationale)


@static("string_collation_order", "MIN/MAX/ORDER BY on character columns under a case-insensitive source collation")
def string_collation_order(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("The source sorts and compares strings case-insensitively by default; Snowflake uses binary "
                 "(case-sensitive) ordering unless a collation is specified, so MIN/MAX and ORDER BY results change.")
    for st in ctx.statements:
        if not st.parsed:
            continue
        for node in st.ast.find_all(exp.Min, exp.Max):
            col = node.this
            if isinstance(col, exp.Column) and type_family(ctx.column_type(col.name)) == "string":
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"{type(node).__name__.upper()}() over character column "
                              f"{col.name}", "strong", rationale)
        for node in st.ast.find_all(exp.Ordered):
            col = node.this
            if isinstance(col, exp.Column) and type_family(ctx.column_type(col.name)) == "string":
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"ORDER BY character column {col.name}", "medium", rationale)


@static("float_aggregation", "SUM/AVG over FLOAT/REAL/DOUBLE values")
def float_aggregation(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Floating-point addition is not associative; engines aggregate in different orders, so exact "
                 "reconciliation of SUM/AVG over FLOAT values fails in the last digits.")
    for st in ctx.statements:
        if not st.parsed:
            continue
        for node in st.ast.find_all(exp.Sum, exp.Avg):
            arg = node.this
            fam = None
            if isinstance(arg, exp.Column):
                fam = type_family(ctx.column_type(arg.name))
            elif isinstance(arg, (exp.Cast, exp.TryCast)) and isinstance(arg.args.get("to"), exp.DataType):
                fam = "float" if arg.args["to"].is_type(*exp.DataType.REAL_TYPES) else None
            if fam == "float":
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"{type(node).__name__.upper()}() over a floating-point value",
                              "strong", rationale)


@static("transaction_semantics", "Explicit transactions, autocommit settings and DDL inside procedures")
def transaction_semantics(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Transaction boundaries differ: Snowflake autocommits each statement outside explicit "
                 "BEGIN/COMMIT, and DDL commits the open transaction implicitly.")
    rules = [
        (r"\bBEGIN\s+TRAN(SACTION)?\b", "medium", "explicit transaction start"),
        (r"^[ \t]*(BT|ET)[ \t]*;", "medium", "Teradata BT/ET transaction bracket"),
        (r"\bCOMMIT(\s+(WORK|TRAN(SACTION)?))?\b", "medium", "COMMIT inside the unit of work"),
        (r"\bROLLBACK\b", "medium", "ROLLBACK semantics"),
        (r"\bSET\s+IMPLICIT_TRANSACTIONS\b", "strong", "implicit transactions setting"),
    ]
    for rx, strength, msg in rules:
        for m in ctx.find(re.compile(rx, re.IGNORECASE | re.MULTILINE)):
            yield hit(m, strength, msg, rationale)
    proc = re.search(r"\bCREATE\s+(OR\s+(REPLACE|ALTER)\s+)?(PROCEDURE|PROC|PACKAGE|FUNCTION)\b", ctx.nostr,
                     re.IGNORECASE)
    if proc:
        for m in ctx.find(r"\b(TRUNCATE\s+TABLE|DROP\s+TABLE|CREATE\s+(GLOBAL\s+TEMPORARY\s+)?TABLE|ALTER\s+TABLE)\b"):
            if m.m.start() > proc.start():
                yield hit(m, "strong", "DDL inside a procedure body (implicit commit in Snowflake)", rationale)


@static("triggers", "CREATE TRIGGER")
def triggers(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bCREATE\s+(OR\s+(REPLACE|ALTER)\s+)?TRIGGER\b"):
        yield hit(m, "strong", "trigger definition",
                  "Snowflake has no triggers; audit/derivation logic must move to streams + tasks or pipelines.")


@static("cursor_loops", "Row-by-row cursor/BULK COLLECT/WHILE loops")
def cursor_loops(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = "Row-by-row processing is slow and credit-hungry in Snowflake; rewrite set-based."
    rules = [
        (r"\bBULK\s+COLLECT\b", "BULK COLLECT"),
        (r"\bFORALL\b", "FORALL loop"),
        (r"\bCURSOR\b", "explicit cursor"),
        (r"\bFETCH\s+(NEXT\s+)?(FROM\s+)?\w+\s+INTO\b", "FETCH ... INTO"),
        (r"\bFOR\s+\w+\s+IN\s*\(\s*SELECT\b", "cursor FOR loop"),
        (r"\bWHILE\s+@@FETCH_STATUS\b", "WHILE @@FETCH_STATUS loop"),
    ]
    for rx, msg in rules:
        for m in ctx.find(rx):
            yield hit(m, "medium", msg, rationale)


@static("identity_columns", "Identity / GENERATED AS IDENTITY columns")
def identity_columns(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = "Generated keys are not gap-free or order-preserving after migration; carry source keys."
    for m in ctx.find(r"\bGENERATED\s+(ALWAYS|BY\s+DEFAULT)\s+AS\s+IDENTITY\b"):
        yield hit(m, "strong", "identity column", rationale)
    for m in ctx.find(r"\bIDENTITY\s*\(\s*\d+\s*,\s*\d+\s*\)"):
        yield hit(m, "medium", "IDENTITY(seed, increment) column", rationale)


@static("recursive_view", "Recursive views and recursive CTEs")
def recursive_view(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bCREATE\s+(OR\s+REPLACE\s+)?RECURSIVE\s+VIEW\b|\bWITH\s+RECURSIVE\b"):
        yield hit(m, "medium", "recursive view / CTE",
                  "Recursive and deeply stacked views perform differently; consider dynamic tables.")
