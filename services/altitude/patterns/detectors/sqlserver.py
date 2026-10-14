"""SQL Server / T-SQL static detectors (batches split on GO; control flow handled by token rules)."""

from __future__ import annotations

import re
from typing import Iterable

from sqlglot import exp

from ..model import Finding
from ..source import SourceContext, type_family
from . import hit, static


def _fam(ctx: SourceContext, node: exp.Expression) -> str | None:
    return type_family(ctx.column_type(node.name)) if isinstance(node, exp.Column) else None


@static("ms_case_insensitive", "String predicates, DISTINCT/GROUP BY/joins on character data under a CI collation")
def ms_case_insensitive(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("SQL Server's default collation is case-insensitive, so string equality, IN/LIKE, DISTINCT, GROUP BY "
                 "and joins treat 'Active' and 'ACTIVE' as equal; Snowflake compares case-sensitively by default.")
    for m in ctx.find(r"\bCOLLATE\s+\w*_CI_\w*"):
        yield hit(m, "strong", "explicit case-insensitive collation", rationale)
    for st in ctx.statements:
        if not st.parsed:
            if st.error != "dot-command":
                for m in ctx.find_in(st, r"(?<![@\w.])\b[\w.\]\[]+\s*(?:=|<>|!=|\bLIKE\b)\s*N?'([^']*)'", view="code"):
                    if re.search(r"[A-Za-z]", m.m.group(1)):
                        yield hit(m, "weak", "string comparison (token rule; statement did not parse)", rationale)
            continue
        for node in st.ast.find_all(exp.EQ, exp.NEQ, exp.Like, exp.In):
            sides = [node.this] + ([node.expression] if node.args.get("expression") is not None else [])
            sides += list(node.args.get("expressions") or [])
            lits = [s for s in sides if isinstance(s, exp.Literal) and s.is_string and re.search(r"[A-Za-z]", s.this)]
            cols = [s for s in sides if isinstance(s, exp.Column) and _fam(ctx, s) in ("string", None)]
            str_cols = [s for s in sides if isinstance(s, exp.Column) and _fam(ctx, s) == "string"]
            if (lits and cols) or len(str_cols) > 1:
                line = ctx.node_line(st, node)
                yield Finding(line, ctx.line_text(line), f"case-sensitive comparison `{node.sql(dialect='tsql')}`",
                              "medium", rationale)
        for node in st.ast.find_all(exp.Distinct, exp.Group):
            cols = [c for c in node.find_all(exp.Column) if _fam(ctx, c) == "string"]
            if cols:
                line = ctx.node_line(st, node)
                what = "DISTINCT" if isinstance(node, exp.Distinct) else "GROUP BY"
                yield Finding(line, ctx.line_text(line), f"{what} on character column {cols[0].name}", "medium",
                              rationale)


@static("ms_datetime_precision", "DATETIME columns/variables and .997/.999 boundary literals")
def ms_datetime_precision(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("DATETIME stores 1/300-second ticks and rounds literals (e.g. '23:59:59.999' becomes next-day "
                 "midnight); Snowflake keeps the literal precision, so boundaries and L3 hashes differ.")
    for m in ctx.find(r"(@?\b\w+)\s+(SMALL)?DATETIME\b(?!2|OFFSET)"):
        yield hit(m, "medium", f"DATETIME column/variable {m.m.group(1)}", rationale)
    for m in ctx.find(r"'\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}\.99[5-9]\d*'", view="code"):
        yield hit(m, "strong", "end-of-period literal rounded by DATETIME", rationale)
    for m in ctx.find(r"\bDATEADD\s*\(\s*(ms|millisecond)\s*,\s*-\s*\d+"):
        yield hit(m, "strong", "DATEADD(ms, -n, ...) boundary", rationale)


@static("ms_nolock", "NOLOCK and isolation hints")
def ms_nolock(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rx = (r"\(\s*NOLOCK\s*\)|\b(READUNCOMMITTED|HOLDLOCK|UPDLOCK|ROWLOCK|TABLOCKX?|PAGLOCK|READPAST)\b"
          r"|\bSET\s+TRANSACTION\s+ISOLATION\s+LEVEL\b")
    for m in ctx.find(rx):
        yield hit(m, "strong", "locking/isolation hint",
                  "Snowflake uses snapshot semantics; locking hints are meaningless and must be removed.")


@static("ms_implicit_conversion", "SET DATEFORMAT/LANGUAGE, ambiguous date literals and string/number comparisons")
def ms_implicit_conversion(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("SQL Server converts implicitly by data-type precedence and session DATEFORMAT/LANGUAGE; Snowflake "
                 "uses its own casting rules and DATE_INPUT_FORMAT=AUTO, so the same literal can mean another value.")
    dateformat = False
    for m in ctx.find(r"\bSET\s+DATEFORMAT\s+\w+"):
        dateformat = True
        yield hit(m, "strong", "session DATEFORMAT", rationale)
    for m in ctx.find(r"\bSET\s+LANGUAGE\s+\w+"):
        yield hit(m, "medium", "session LANGUAGE (affects date parsing)", rationale)
    for m in ctx.find(r"'\d{1,2}[/.]\d{1,2}[/.]\d{2,4}'", view="code"):
        yield hit(m, "strong" if dateformat else "medium", "ambiguous dd/mm vs mm/dd date literal", rationale)
    for st in ctx.statements:
        if not st.parsed:
            continue
        for node in st.ast.find_all(exp.EQ, exp.NEQ, exp.GT, exp.LT, exp.GTE, exp.LTE):
            a, b = node.this, node.expression
            for col, lit in ((a, b), (b, a)):
                if not (isinstance(col, exp.Column) and isinstance(lit, exp.Literal)):
                    continue
                fam = _fam(ctx, col)
                if (fam == "string" and not lit.is_string) or (fam in ("integer", "decimal") and lit.is_string):
                    line = ctx.node_line(st, node)
                    yield Finding(line, ctx.line_text(line), f"implicit string/number conversion in "
                                  f"`{node.sql(dialect='tsql')}`", "medium", rationale)


@static("ms_error_handling", "TRY/CATCH, @@ERROR, @@ROWCOUNT, RAISERROR, THROW")
def ms_error_handling(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bBEGIN\s+(TRY|CATCH)\b|@@(ERROR|ROWCOUNT|TRANCOUNT)\b|\bRAISERROR\b|\bTHROW\b"):
        yield hit(m, "strong", "T-SQL error handling",
                  "Rebuild with Snowflake Scripting EXCEPTION blocks and SQLROWCOUNT.")


@static("ms_dynamic_sql", "EXEC(@sql), EXEC @sql and sp_executesql")
def ms_dynamic_sql(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rx = re.compile(r"\bEXEC(UTE)?\s*\(\s*@\w+|\bsp_executesql\b|\bEXEC(UTE)?\s+@\w+\s*(;|$)", re.I | re.M)
    for m in ctx.find(rx):
        yield hit(m, "strong", "dynamic SQL",
                  "Strings built at runtime escape static conversion; review and use EXECUTE IMMEDIATE with binds.")


@static("ms_ssis_script_task", "SSIS script tasks/components in .dtsx XML")
def ms_ssis_script_task(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"Microsoft\.ScriptTask|\bScriptComponent\b|<ScriptProject\b", view="code"):
        yield hit(m, "strong", "SSIS script task",
                  "C# script tasks hold business logic that automated conversion cannot see; re-engineer.")


@static("constraints_enforcement", "Cascading FKs, triggers and constraints that Snowflake does not enforce")
def constraints_enforcement(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Snowflake does not enforce PRIMARY KEY/UNIQUE/FOREIGN KEY/CHECK (only NOT NULL) and has no "
                 "cascades or triggers; integrity the source enforced must move to pipeline logic and DQ rules.")
    rules = [
        (r"\bON\s+(DELETE|UPDATE)\s+CASCADE\b", "strong", "cascading foreign key"),
        (r"\bCREATE\s+(OR\s+ALTER\s+)?TRIGGER\b", "strong", "trigger"),
        (r"\bFOREIGN\s+KEY\b|\bREFERENCES\s+[\w.\[\]\"]+", "medium", "foreign key"),
        (r"\bPRIMARY\s+KEY\b|\bUNIQUE\b", "medium", "primary key / unique constraint"),
        (r"\bCHECK\s*\(", "medium", "check constraint"),
    ]
    for rx, strength, msg in rules:
        for m in ctx.find(rx):
            yield hit(m, strength, msg, rationale)


@static("ms_synapse_distribution", "Synapse distribution, columnstore and index DDL")
def ms_synapse_distribution(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = "Distribution and index tuning do not apply to Snowflake; remove and measure."
    for m in ctx.find(r"\bDISTRIBUTION\s*=\s*(HASH|ROUND_ROBIN|REPLICATE)\b|\bCLUSTERED\s+COLUMNSTORE\s+INDEX\b"):
        yield hit(m, "strong", "Synapse distribution/columnstore", rationale)
    for m in ctx.find(r"\bCREATE\s+(UNIQUE\s+)?(NON)?CLUSTERED\s+INDEX\b"):
        yield hit(m, "medium", "index DDL", rationale)
