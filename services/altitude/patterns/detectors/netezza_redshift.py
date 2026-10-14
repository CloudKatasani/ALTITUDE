"""Netezza and Redshift static detectors."""

from __future__ import annotations

import re
from typing import Iterable

from ..model import Finding
from ..source import SourceContext
from . import hit, static


@static("nz_distribution", "DISTRIBUTE ON / ORGANIZE ON / GROOM / GENERATE STATISTICS")
def nz_distribution(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bDISTRIBUTE\s+ON\b|\bORGANIZE\s+ON\b|\bGROOM\s+TABLE\b|\bGENERATE\s+(EXPRESS\s+)?STATISTICS\b"):
        yield hit(m, "strong", "Netezza distribution/zone-map maintenance",
                  "Distribution keys and zone maps are irrelevant in Snowflake; drop them and measure.")


@static("nz_nzplsql", "NZPLSQL procedures")
def nz_nzplsql(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bLANGUAGE\s+NZPLSQL\b|\bBEGIN_PROC\b"):
        yield hit(m, "strong", "NZPLSQL procedure", "NZPLSQL must be rewritten in Snowflake Scripting.")


@static("nz_shell", "nzsql/nzload/nz_migrate shell orchestration")
def nz_shell(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\b(nzsql|nzload|nz_migrate|nzsession|nzbackup)\b", flags=0):
        yield hit(m, "strong", f"{m.m.group(1)} invocation",
                  "Shell-level control flow and error handling must be rebuilt in an orchestrator; nzload becomes COPY.")


@static("nz_date_behaviour", "Day-of-week numbering and Netezza date-part semantics")
def nz_date_behaviour(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Netezza numbers days of the week 1-7 with Sunday = 1; Snowflake DAYOFWEEK/EXTRACT(DOW) return 0-6 "
                 "(WEEK_START = 0), so weekday buckets shift by one.")
    for m in ctx.find(r"\bEXTRACT\s*\(\s*DOW\b|\bDATE_PART\s*\(\s*'dow'", view="code"):
        yield hit(m, "strong", "day-of-week extraction", rationale)
    for m in ctx.find(r"\bTO_CHAR\s*\([^)]*,\s*'D'\s*\)", view="code"):
        yield hit(m, "strong", "TO_CHAR(..., 'D') day number", rationale)


@static("quoted_identifiers", "Quoted identifiers with lower-case letters / case-sensitive identifier settings")
def quoted_identifiers(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    rationale = ("Redshift folds unquoted identifiers to lower case and Snowflake to upper case; quoted mixed-case "
                 "names only resolve when every reference quotes them identically.")
    for m in ctx.find(r"\benable_case_sensitive_identifier\b"):
        yield hit(m, "strong", "case-sensitive identifier setting", rationale)
    seen: set[int] = set()
    for m in ctx.find(r'"[^"\n]*[a-z][^"\n]*"', view="code", flags=0):
        if m.line not in seen:
            seen.add(m.line)
            yield hit(m, "medium", f"quoted identifier {m.m.group(0)}", rationale)


@static("rs_varchar_length", "VARCHAR(n)/CHAR(n) declarations (byte lengths in Redshift)")
def rs_varchar_length(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\b(VAR)?CHAR(ACTER)?\s*\(\s*\d+\s*\)"):
        yield hit(m, "weak", "length declared in bytes",
                  "Redshift VARCHAR(n) counts bytes; Snowflake counts characters. Re-derive from profiled data.")


@static("rs_late_binding_views", "WITH NO SCHEMA BINDING")
def rs_late_binding_views(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\bWITH\s+NO\s+SCHEMA\s+BINDING\b"):
        yield hit(m, "strong", "late-binding view", "Snowflake views bind at creation; deploy in dependency order.")


@static("rs_unload", "UNLOAD statements")
def rs_unload(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(re.compile(r"^\s*UNLOAD\s*\(", re.I | re.M)):
        yield hit(m, "strong", "UNLOAD to S3", "Re-point extracts to COPY INTO @stage or data sharing.")


@static("rs_dist_sort", "DISTKEY / SORTKEY / DISTSTYLE / ENCODE")
def rs_dist_sort(ctx: SourceContext, rubrics) -> Iterable[Finding]:
    for m in ctx.find(r"\b(DISTKEY|SORTKEY|DISTSTYLE|INTERLEAVED|ENCODE\s+\w+)\b"):
        yield hit(m, "strong", f"{m.m.group(1).split()[0].upper()} clause",
                  "Distribution, sort and encoding settings have no Snowflake equivalent; remove and measure.")
