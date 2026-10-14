"""Profile detectors: rules over harvested metadata and aggregate statistics (never row data).

Profile format (every key optional)::

    tables:   [{name, kind: SET|MULTISET, source_row_count, target_row_count}]
    columns:  [{table, column, source_type, target_type,
                attributes: {casespecific: bool, collation: str},
                source_stats: {null_count, empty_string_count, max_scale, has_time_component,
                               max_byte_length, max_char_length},
                target_stats: {null_count, empty_string_count}}]
    views:    [{name, depth}]
    workloads: [{name, priority}]
    settings: {time_zone, nls_date_format, nls_sort, nls_comp, collation}
    platform: {features: [...], diagnostics_pack_used, licensed_options: [...], end_of_support, as_of}
    ssis_packages: [{name, script_tasks}]
    constraints: [{table, kind, on_delete}]
    triggers:  [{name, table}]
    update_sources: [{statement, source, key, row_count, distinct_keys}]
"""

from __future__ import annotations

import re
from datetime import date
from typing import Iterable

from ..model import Finding
from ..source import type_family
from . import profile

_SCALE = re.compile(r"\(\s*\d+\s*,\s*(\d+)\s*\)")


def _f(where: str, strength: str, message: str, rationale: str) -> Finding:
    return Finding(0, where, message, strength, rationale)


def _target_scale(type_text: str | None) -> int | None:
    if not type_text:
        return None
    m = _SCALE.search(type_text)
    if m:
        return int(m.group(1))
    fam = type_family(type_text)
    if fam == "integer" or re.match(r"^\s*(NUMBER|NUMERIC|DECIMAL)\s*(\(\s*\d+\s*\))?\s*$", type_text, re.I):
        return 0
    return None


@profile("set_table_duplicates", "SET tables in DBC.TablesV, and target rows above source distinct rows")
def set_table_duplicates(p: dict, rubrics) -> Iterable[Finding]:
    for t in p.get("tables", []):
        if str(t.get("kind", "")).upper() != "SET":
            continue
        src, tgt = t.get("source_row_count"), t.get("target_row_count")
        if src is not None and tgt is not None and tgt > src:
            yield _f(t["name"], "strong", f"SET table {t['name']}: target has {tgt - src} more rows than the source",
                     "Rows that the SET table discarded are present in Snowflake.")
        else:
            yield _f(t["name"], "medium", f"SET table {t['name']}", "Table kind SET in the catalogue harvest.")


@profile("case_insensitive_columns", "Case-insensitive character columns/collations in the catalogue")
def case_insensitive_columns(p: dict, rubrics) -> Iterable[Finding]:
    coll = str(p.get("settings", {}).get("collation", ""))
    if re.search(r"_CI_", coll, re.I):
        yield _f("database", "strong", f"case-insensitive default collation {coll}",
                 "Every character comparison in the source ignores case unless overridden.")
    for c in p.get("columns", []):
        attrs = c.get("attributes") or {}
        if attrs.get("casespecific") is False or re.search(r"_CI_", str(attrs.get("collation", "")), re.I):
            yield _f(f"{c['table']}.{c['column']}", "strong", f"case-insensitive column {c['table']}.{c['column']}",
                     "Catalogue marks the column NOT CASESPECIFIC / case-insensitive collation.")


@profile("char_padding", "CHAR(n) source columns mapped to VARCHAR")
def char_padding(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        if re.match(r"^\s*CHAR(ACTER)?\s*\(", str(c.get("source_type", "")), re.I) and \
                re.match(r"^\s*(VARCHAR|STRING|TEXT)", str(c.get("target_type", "")), re.I):
            yield _f(f"{c['table']}.{c['column']}", "medium", f"CHAR column {c['table']}.{c['column']} becomes VARCHAR",
                     "Pad characters survive the export unless the load applies RTRIM.")


@profile("null_count_delta", "Snowflake null count below the source null count for the same column")
def null_count_delta(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        s, t = c.get("source_stats") or {}, c.get("target_stats") or {}
        sn, tn = s.get("null_count"), t.get("null_count")
        empties = t.get("empty_string_count") or 0
        if sn is not None and tn is not None and tn < sn:
            yield _f(f"{c['table']}.{c['column']}", "strong",
                     f"{c['table']}.{c['column']}: target nulls {tn} < source nulls {sn}",
                     f"{empties} empty strings in the target account for the NULLs Oracle stored for ''.")
        elif empties:
            yield _f(f"{c['table']}.{c['column']}", "medium", f"{c['table']}.{c['column']}: {empties} empty strings",
                     "Oracle cannot hold ''; these values were NULL in the source.")


@profile("max_scale", "Profiled max scale above the target column scale")
def max_scale(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        ms = (c.get("source_stats") or {}).get("max_scale")
        ts = _target_scale(c.get("target_type"))
        if ms is not None and ts is not None and ms > ts:
            yield _f(f"{c['table']}.{c['column']}", "strong",
                     f"{c['table']}.{c['column']}: source scale {ms} > target scale {ts}",
                     "Decimals beyond the target scale are rounded away on load.")


@profile("date_time_component", "DATE with time-of-day values mapped to DATE")
def date_time_component(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        if (c.get("source_stats") or {}).get("has_time_component") and \
                type_family(c.get("target_type")) == "date":
            yield _f(f"{c['table']}.{c['column']}", "strong", f"{c['table']}.{c['column']}: time of day would be lost",
                     "Profile shows non-midnight values while the target type is DATE.")


@profile("view_depth", "View dependency depth above the rubric limit")
def view_depth(p: dict, rubrics) -> Iterable[Finding]:
    limit = rubrics.get("rubric.patterns.profile.view_depth_max")
    for v in p.get("views", []):
        if v.get("depth", 0) > limit:
            yield _f(v["name"], "strong", f"view {v['name']} depth {v['depth']} > {limit}",
                     "Deep view stacks are re-planned on every query in Snowflake.")


@profile("update_source_uniqueness", "UPDATE/MERGE sources that are not unique on the join key")
def update_source_uniqueness(p: dict, rubrics) -> Iterable[Finding]:
    for u in p.get("update_sources", []):
        rows, keys = u.get("row_count"), u.get("distinct_keys")
        if rows is not None and keys is not None and keys < rows:
            yield _f(f"{u.get('statement')}:{u.get('source')}", "strong",
                     f"{u.get('source')} has {rows - keys} duplicate key rows for {', '.join(u.get('key', []))}",
                     "A multi-match source makes the update nondeterministic in Snowflake.")


@profile("tasm_workloads", "TASM/TIWM workload definitions")
def tasm_workloads(p: dict, rubrics) -> Iterable[Finding]:
    wl = p.get("workloads", [])
    if wl:
        yield _f("TASM", "strong", f"{len(wl)} TASM workload definitions",
                 "Workload priorities must be mapped to warehouses and resource monitors.")


@profile("session_timezone", "Non-UTC session/system time zone")
def session_timezone(p: dict, rubrics) -> Iterable[Finding]:
    tz = (p.get("settings") or {}).get("time_zone")
    if tz and str(tz).upper() not in {"UTC", "GMT", "00:00", "+00:00", "ETC/UTC"}:
        yield _f("settings.time_zone", "strong", f"source time zone {tz}",
                 "Timestamps and day boundaries were evaluated in a non-UTC zone.")


@profile("nls_settings", "Non-default NLS settings")
def nls_settings(p: dict, rubrics) -> Iterable[Finding]:
    s = p.get("settings") or {}
    for key in ("nls_date_format", "nls_sort", "nls_comp", "nls_timestamp_format"):
        if s.get(key) and str(s[key]).upper() not in {"BINARY"}:
            yield _f(f"settings.{key}", "strong", f"{key.upper()} = {s[key]}",
                     "Format-less conversions and comparisons depend on this NLS setting.")


@profile("exadata_features", "Exadata smart scan / HCC / storage indexes in use")
def exadata_features(p: dict, rubrics) -> Iterable[Finding]:
    feats = {str(f).lower() for f in (p.get("platform") or {}).get("features", [])}
    hits = feats & {"smart_scan", "hcc", "storage_indexes", "flash_cache"}
    if hits:
        yield _f("platform", "strong", f"Exadata features: {', '.join(sorted(hits))}",
                 "Performance relied on Exadata offload; plan clustering only after measurement.")


@profile("licensing_exposure", "Oracle Diagnostics/Tuning Pack use without licence")
def licensing_exposure(p: dict, rubrics) -> Iterable[Finding]:
    plat = p.get("platform") or {}
    licensed = {str(x).lower() for x in plat.get("licensed_options", [])}
    if plat.get("diagnostics_pack_used") and "diagnostics_pack" not in licensed:
        yield _f("platform", "strong", "Diagnostics Pack (AWR/ASH) used without a recorded licence",
                 "Licence exposure must be reviewed in Phase 0.")


@profile("datetime_columns", "DATETIME/SMALLDATETIME source columns")
def datetime_columns(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        if re.match(r"^\s*(SMALL)?DATETIME\s*$", str(c.get("source_type", "")), re.I):
            yield _f(f"{c['table']}.{c['column']}", "medium", f"DATETIME column {c['table']}.{c['column']}",
                     "1/300-second rounding in the source; reconcile with tolerance.")


@profile("ssis_script_tasks", "SSIS packages with script tasks")
def ssis_script_tasks(p: dict, rubrics) -> Iterable[Finding]:
    for pkg in p.get("ssis_packages", []):
        if pkg.get("script_tasks"):
            yield _f(pkg["name"], "strong", f"SSIS package {pkg['name']}: {pkg['script_tasks']} script task(s)",
                     "Script tasks need re-engineering.")


@profile("unenforced_constraints", "Enforced cascades, triggers and constraints in the source catalogue")
def unenforced_constraints(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("constraints", []):
        cascade = str(c.get("on_delete", "")).lower() == "cascade" or str(c.get("on_update", "")).lower() == "cascade"
        yield _f(c.get("table", "?"), "strong" if cascade else "medium",
                 f"{c.get('kind', 'constraint')} on {c.get('table')}{' with cascade' if cascade else ''}",
                 "Snowflake does not enforce this constraint.")
    for t in p.get("triggers", []):
        yield _f(t.get("table", "?"), "strong", f"trigger {t.get('name')} on {t.get('table')}",
                 "Trigger logic must move to pipelines or streams/tasks.")


@profile("end_of_support", "Platform end of support inside the rubric horizon")
def end_of_support(p: dict, rubrics) -> Iterable[Finding]:
    plat = p.get("platform") or {}
    if not plat.get("end_of_support") or not plat.get("as_of"):
        return
    eos, as_of = date.fromisoformat(str(plat["end_of_support"])), date.fromisoformat(str(plat["as_of"]))
    horizon = rubrics.get("rubric.patterns.profile.end_of_support_horizon_days")
    days = (eos - as_of).days
    if days <= horizon:
        yield _f("platform", "strong", f"end of support {eos.isoformat()} in {days} days",
                 "Deadline pressure favours lift-and-shift plus a refactor backlog.")


@profile("varchar_multibyte", "Byte length differs from character length")
def varchar_multibyte(p: dict, rubrics) -> Iterable[Finding]:
    for c in p.get("columns", []):
        s = c.get("source_stats") or {}
        if s.get("max_byte_length") is not None and s.get("max_char_length") is not None \
                and s["max_byte_length"] != s["max_char_length"]:
            yield _f(f"{c['table']}.{c['column']}", "strong", f"{c['table']}.{c['column']}: multibyte data",
                     "Lengths were declared in bytes; re-derive character lengths.")
