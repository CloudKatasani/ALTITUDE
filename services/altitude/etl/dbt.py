"""dbt project generation from mapping graphs (Section 11.1).

Layers follow ``knowledge/etl/dbt_conventions.yaml``: ``stg_<system>__<table>`` (one per source table, views),
``int_<mart>`` (the mapping logic as CTEs, views) and ``dim_/fct_/agg_`` marts (tables, tagged with the
package / workflow names so schedulers can run them). Tests are derived from evidence, not guessed:

- ``unique`` + ``not_null``: target key metadata, sequence-generated keys, or (SSIS, no metadata) a column
  that traces back to a source primary key without row fan-out; ``unique`` for a sole GROUP BY column;
- ``not_null``: NOT NULL target columns;
- ``relationships``: target foreign-key metadata, or a column tracing to a source foreign key whose parent
  key is a complete (unfiltered) key of another generated model, or a lookup on a generated model's key;
- ``accepted_values``: columns whose every branch is a string literal (CASE/IIF/DECODE).

Every file is header-stamped ``AUTO-GENERATED — DO NOT EDIT`` (principle 8).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from altitude.core.generated import stamp
from altitude.core.rubric import RubricSet

from . import kb
from .classify import JobAssessment, assess
from .graph import Column, MappingGraph, Node, PackageParse
from .naming import ident, singular
from .sqlgen import GenerationError, Lineage, SqlBuilder, trace


@dataclass
class ColumnSpec:
    name: str
    type: str = "VARCHAR"
    description: str = ""
    tests: list[Any] = field(default_factory=list)

    def add_test(self, test: Any) -> None:
        if test not in self.tests:
            self.tests.append(test)


@dataclass
class ModelSpec:
    name: str
    layer: str                       # staging|intermediate|marts
    folder: str
    sql: str
    columns: list[ColumnSpec]
    description: str
    tags: list[str] = field(default_factory=list)
    job: str | None = None
    materialized: str = "view"
    target: Any = field(default=None, repr=False)   # (graph, target node id, target columns) for marts


@dataclass
class SourceTable:
    system: str
    table: str
    raw_name: str
    columns: dict[str, Column] = field(default_factory=dict)
    description: str = ""


@dataclass
class DbtProject:
    name: str
    files: dict[str, str]
    models: dict[str, ModelSpec]
    sources: dict[tuple[str, str], SourceTable]
    assessments: list[JobAssessment]
    skipped: list[dict[str, str]]
    vars: dict[str, Any]
    domains: dict[str, list[str]]


# --------------------------------------------------------------------------- naming


def mart_name(table: str, graph: MappingGraph, target: Node) -> str:
    conv = kb.conventions()
    for rule in conv["target_prefixes"]:
        if re.search(rule["pattern"], table):
            base = re.sub(rule["pattern"], "", table) or table
            return rule["prefix"] + base
    fb = conv["fallback_prefix"]
    if graph.by_kind("aggregate"):
        return fb["aggregate"] + table
    if any(c.key == "foreign" for c in target.props.get("columns", [])):
        return fb["with_foreign_keys"] + table
    return fb["default"] + table


def stg_name(system: str, table: str) -> str:
    return f"{kb.conventions()['layers']['staging'].get('prefix', 'stg_')}{system}__{table}"


def _ref(model: str) -> str:
    return "{{ ref('" + model + "') }}"


# --------------------------------------------------------------------------- key inference


def infer_keys(sources: dict[tuple[str, str], SourceTable]) -> None:
    """Fill primary/foreign keys by naming convention for tables whose export carried no key metadata."""
    conv = kb.conventions()["key_inference"]
    strip = conv.get("table_prefixes_to_strip", [])

    def bare(table: str) -> str:
        for p in strip:
            if table.startswith(p):
                return table[len(p):]
        return table

    pks: dict[str, tuple[str, str]] = {}
    for (system, table), st in sources.items():
        if any(c.key for c in st.columns.values()):
            for c in st.columns.values():
                if c.key == "primary":
                    pks.setdefault(singular(bare(table)), (table, c.name))
            continue
        ent = singular(bare(table))
        for c in st.columns.values():
            if any(re.fullmatch(p.format(table=re.escape(ent)), c.name) for p in conv["primary"]):
                c.key = "primary"
                c.nullable = False
                pks.setdefault(ent, (table, c.name))
                break
    for (system, table), st in sources.items():
        if any(c.key == "foreign" for c in st.columns.values()):
            continue
        for c in st.columns.values():
            if c.key:
                continue
            for p in conv["foreign"]:
                m = re.fullmatch(p, c.name)
                if m and m.groupdict().get("table"):
                    ref = pks.get(singular(m.group("table")))
                    if ref and ref[0] != table:
                        c.key, c.ref_table, c.ref_column = "foreign", ref[0], ref[1]
                        break


# --------------------------------------------------------------------------- generation


def generate_dbt_project(packages: list[PackageParse], project_name: str = "altitude_migration",
                         usage: dict[str, int] | None = None, rubrics: RubricSet | None = None) -> DbtProject:
    conv = kb.conventions()
    assessments = assess(packages, usage, rubrics)
    by_job = {a.job: a for a in assessments}
    graphs = [g for p in packages for g in p.graphs]
    skipped: list[dict[str, str]] = [
        {"job": a.job, "reason": f"{a.recommendation}: {a.rationale}"}
        for a in assessments if a.kind == "data_flow" and a.recommendation != "lift"]
    candidates = [g for g in graphs if by_job[g.job].recommendation == "lift"]

    # target table -> mart model; drop graphs that fail until the set is stable
    while True:
        marts: dict[str, tuple[str, MappingGraph, Node]] = {}
        for g in candidates:
            for t in g.by_kind("target"):
                table = t.props["table"]
                if table in marts:
                    skipped.append({"job": g.job, "reason": f"target {table} is also loaded by {marts[table][1].job}"})
                    continue
                marts[table] = (mart_name(table, g, t), g, t)
        failed, built = [], {}
        for g in candidates:
            try:
                built[g.job] = _build_graph(g, marts)
            except GenerationError as e:
                failed.append(g)
                skipped.append({"job": g.job, "reason": f"generation failed: {e}"})
        if not failed:
            break
        candidates = [g for g in candidates if g not in failed]

    sources: dict[tuple[str, str], SourceTable] = {}
    for g in candidates:
        for key, st in built[g.job]["sources"].items():
            cur = sources.setdefault(key, SourceTable(*key, st.raw_name, {}, st.description))
            for c in st.columns.values():
                cur.columns.setdefault(c.name, Column(**vars(c)))
    infer_keys(sources)

    models: dict[str, ModelSpec] = {}
    for (system, table), st in sorted(sources.items()):
        name = stg_name(system, table)
        cols = list(st.columns.values())
        sql = "SELECT\n" + ",\n".join(f"    {c.name}" for c in cols) + "\nFROM {{ source('" + system + "', '" + table + "') }}\n"
        specs = []
        for c in cols:
            spec = ColumnSpec(c.name, c.type, c.description or f"{st.raw_name}.{c.name}")
            if c.key == "primary":
                for t in conv["tests"]["primary_key"]:
                    spec.add_test(t)
            if c.key == "foreign" and c.ref_table and (system, c.ref_table) in sources:
                spec.add_test({"relationships": {"to": f"ref('{stg_name(system, c.ref_table)}')", "field": c.ref_column}})
            specs.append(spec)
        models[name] = ModelSpec(name, "staging", f"{conv['layers']['staging']['folder']}/{system}", sql, specs,
                                 f"Staging view over {system}.{st.raw_name} (renamed to snake_case, no logic).",
                                 materialized=conv["layers"]["staging"]["materialized"])

    lineage: dict[str, dict[str, Lineage]] = {}
    for g in candidates:
        for tid, ts in built[g.job]["targets"].items():
            table = g.nodes[tid].props["table"]
            mart = marts[table][0]
            int_name = f"{conv['layers']['intermediate'].get('prefix', 'int_')}{mart}"
            tcols = {c.name: c for c in g.nodes[tid].props.get("columns", [])}
            lineage[mart] = {c: trace(g, tid, c) for c in ts.columns}
            int_cols = [ColumnSpec(c, tcols[c].type if c in tcols else "VARCHAR", _describe(lineage[mart][c], g, c))
                        for c in ts.columns]
            models[int_name] = ModelSpec(int_name, "intermediate", conv["layers"]["intermediate"]["folder"], ts.sql,
                                         int_cols, f"Logic of {g.tool} job `{g.job}` for target {table}.",
                                         tags=list(g.tags), job=g.job,
                                         materialized=conv["layers"]["intermediate"]["materialized"])
            tags = list(dict.fromkeys(g.tags + ([ident(g.package)] if g.package else [])))
            config = "{{ config(materialized='" + conv["layers"]["marts"]["materialized"] + "', tags=" + json.dumps(tags).replace('"', "'") + ") }}"
            sql = config + "\n\nSELECT\n" + ",\n".join(f"    {c}" for c in ts.columns) + "\nFROM " + _ref(int_name) + "\n"
            mcols = [ColumnSpec(c, tcols[c].type if c in tcols else "VARCHAR",
                                (tcols[c].description if c in tcols and tcols[c].description else "")
                                or _describe(lineage[mart][c], g, c)) for c in ts.columns]
            models[mart] = ModelSpec(mart, "marts", conv["layers"]["marts"]["folder"], sql, mcols,
                                     g.nodes[tid].props.get("description") or f"{table} loaded by `{g.job}`.",
                                     tags=tags, job=g.job, materialized=conv["layers"]["marts"]["materialized"])
            models[mart].target = (g, tid, tcols)

    _mart_tests(models, marts, sources, lineage, conv)

    variables: dict[str, Any] = {}
    domains: dict[str, list[str]] = {}
    for g in candidates:
        for k, v in g.variables.items():
            variables.setdefault(k, v)
        for col, vals in g.domains.items():
            cur = domains.setdefault(col, [])
            cur += [v for v in vals if v not in cur]
    project = DbtProject(project_name, {}, models, sources, assessments, skipped, variables, domains)
    project.files = render_files(project, packages)
    return project


def _build_graph(g: MappingGraph, marts: dict[str, tuple[str, MappingGraph, Node]]) -> dict[str, Any]:
    local: dict[tuple[str, str], SourceTable] = {}

    def relation_for(node: Node) -> str:
        table = node.props["table"]
        if table in marts:
            if marts[table][1] is g:
                raise GenerationError(f"{g.job}: reads its own target {table} (incremental logic)")
            return _ref(marts[table][0])
        key = (node.props.get("system") or "source", table)
        st = local.setdefault(key, SourceTable(key[0], table, node.props.get("raw_table") or table, {},
                                               node.props.get("description", "")))
        for c in node.props.get("columns") or node.props.get("lookup_columns") or []:
            st.columns.setdefault(c.name, c)
        return _ref(stg_name(*key))

    targets = {t.id: SqlBuilder(g, relation_for).build_target(t.id) for t in g.by_kind("target")}
    return {"targets": targets, "sources": local}


def _describe(lin: Lineage, g: MappingGraph, col: str) -> str:
    if lin.kind == "source":
        return f"From source {lin.system}.{lin.table}.{lin.column}."
    if lin.kind == "lookup":
        return f"Looked up from {lin.table}.{lin.column}."
    if lin.kind == "sequence":
        return "Surrogate key (sequence generator -> ROW_NUMBER())."
    if lin.kind == "aggregate":
        return "Aggregated measure."
    if lin.kind == "expr":
        return "Derived by expression" + (f"; values {', '.join(lin.literal_values)}." if lin.literal_values else ".")
    return f"Column {col}."


def _mart_tests(models: dict[str, ModelSpec], marts: dict, sources: dict, lineage: dict, conv: dict) -> None:
    table_to_mart = {t: m[0] for t, m in marts.items()}
    key_index: dict[tuple[str, str], tuple[str, str]] = {}     # (source table, column) -> (mart, column)
    mart_keys: dict[tuple[str, str], tuple[str, str]] = {}     # (mart table, column) -> (mart, column)
    src_cols = {(t, c): col for (s, t), st in sources.items() for c, col in st.columns.items()}
    marts_only = [m for m in models.values() if m.layer == "marts"]
    for m in marts_only:
        g, tid, tcols = m.target
        has_meta = any(c.key for c in tcols.values())
        table = g.nodes[tid].props["table"]
        for spec in m.columns:
            lin = lineage[m.name][spec.name]
            meta = tcols.get(spec.name)
            unique = False
            if meta is not None and meta.key == "primary":
                unique = True
            elif lin.kind == "sequence":
                unique = True
            elif not has_meta and lin.kind == "source" and not lin.fanout:
                src = src_cols.get((lin.table, lin.column))
                parent = mart_keys.get((lin.table, lin.column))
                unique = (src is not None and src.key == "primary") or parent is not None
            if unique:
                for t in conv["tests"]["primary_key"]:
                    spec.add_test(t)
                mart_keys[(table, spec.name)] = (m.name, spec.name)
                if lin.kind == "source" and not lin.rows_dropped and not lin.fanout:
                    key_index.setdefault((lin.table, lin.column), (m.name, spec.name))
            elif lin.grouped_single:
                spec.add_test("unique")
                mart_keys[(table, spec.name)] = (m.name, spec.name)
            if meta is not None and not meta.nullable:
                spec.add_test("not_null")
            if lin.kind == "expr" and lin.literal_values:
                spec.add_test({"accepted_values": {"values": list(lin.literal_values)}})
    for m in marts_only:
        g, tid, tcols = m.target
        for spec in m.columns:
            lin = lineage[m.name][spec.name]
            meta = tcols.get(spec.name)
            parent = None
            if meta is not None and meta.key == "foreign" and meta.ref_table in table_to_mart:
                pm = table_to_mart[meta.ref_table]
                if any(c.name == meta.ref_column for c in models[pm].columns):
                    parent = (pm, meta.ref_column)
            elif lin.kind == "source":
                src = src_cols.get((lin.table, lin.column))
                if src is not None and src.key == "foreign" and src.ref_table:
                    parent = key_index.get((src.ref_table, src.ref_column))
            elif lin.kind == "lookup" and lin.table in table_to_mart:
                parent = mart_keys.get((lin.table, lin.column))
            if parent and parent[0] != m.name:
                spec.add_test({"relationships": {"to": f"ref('{parent[0]}')", "field": parent[1]}})


# --------------------------------------------------------------------------- rendering


def _yaml(obj: Any) -> str:
    return yaml.safe_dump(obj, sort_keys=False, default_flow_style=False, width=120, allow_unicode=True)


def _columns_yaml(cols: list[ColumnSpec]) -> list[dict]:
    out = []
    for c in cols:
        d: dict[str, Any] = {"name": c.name, "description": c.description, "data_type": c.type}
        if c.tests:
            d["data_tests"] = c.tests
        out.append(d)
    return out


def render_files(project: DbtProject, packages: list[PackageParse]) -> dict[str, str]:
    conv = kb.conventions()
    src_label = "etl:" + ",".join(sorted({p.source_file for p in packages}))
    files: dict[str, str] = {}

    def put(path: str, content: str) -> None:
        suffix = "." + path.rsplit(".", 1)[-1]
        files[path] = stamp(content, suffix, src_label)

    put("dbt_project.yml", _yaml({
        "name": project.name, "version": "1.0.0", "config-version": conv["project"]["config_version"],
        "profile": conv["project"]["profile"], "model-paths": ["models"], "macro-paths": ["macros"],
        "vars": {k: v for k, v in sorted(project.vars.items())},
        "models": {project.name: {
            conv["layers"][layer]["folder"]: {"+materialized": conv["layers"][layer]["materialized"]}
            for layer in ("staging", "intermediate", "marts")}},
    }))
    systems = sorted({s for s, _ in project.sources})
    for system in systems:
        tables = [st for (s, _), st in sorted(project.sources.items()) if s == system]
        put(f"models/{conv['layers']['staging']['folder']}/{system}/_{system}__sources.yml", _yaml({
            "version": 2,
            "sources": [{"name": system, "schema": system, "description": f"Raw landing of source system {system}.",
                         "tables": [{"name": st.table, "description": st.description or st.raw_name,
                                     "columns": [{"name": c.name, "data_type": c.type} for c in st.columns.values()]}
                                    for st in tables]}],
        }))
        stg = [m for m in project.models.values() if m.layer == "staging" and m.folder.endswith(f"/{system}")]
        put(f"models/{conv['layers']['staging']['folder']}/{system}/_{system}__models.yml", _yaml({
            "version": 2,
            "models": [{"name": m.name, "description": m.description, "columns": _columns_yaml(m.columns)}
                       for m in sorted(stg, key=lambda x: x.name)],
        }))
    for m in project.models.values():
        put(f"models/{m.folder}/{m.name}.sql", m.sql)
    for layer in ("intermediate", "marts"):
        ms = sorted((m for m in project.models.values() if m.layer == layer), key=lambda x: x.name)
        if ms:
            folder = conv["layers"][layer]["folder"]
            put(f"models/{folder}/_{folder}__models.yml", _yaml({
                "version": 2,
                "models": [{"name": m.name, "description": '{{ doc("' + m.name + '") }}',
                            "columns": _columns_yaml(m.columns)} for m in ms],
            }))
    docs = []
    by_job = {a.job: a for a in project.assessments}
    for m in sorted((m for m in project.models.values() if m.layer != "staging"), key=lambda x: x.name):
        a = by_job.get(m.job)
        lines = [f"{{% docs {m.name} %}}", m.description, ""]
        if a:
            lines += [f"- Source: {a.tool} `{a.job}` ({a.source_file})",
                      f"- Classification: **{a.classification}**, recommendation **{a.recommendation}** "
                      f"(confidence {a.confidence:.2f}, complexity {a.complexity_score:g})",
                      f"- Rationale: {a.rationale}"]
            if a.issues:
                lines.append("- Known issues: " + "; ".join(f"{i.id} ({i.severity}) {i.message}" for i in a.issues))
        lines += ["{% enddocs %}", ""]
        docs.append("\n".join(lines))
    put("models/_docs.md", "\n".join(docs))
    for pkg in packages:
        for task in pkg.control_tasks:
            if task.kind == "sql_task" and task.converted_sql and task.recommendation_hint == "lift":
                name = f"{ident(pkg.package)}__{ident(task.name)}"
                body = (f"{{% macro {name}() %}}\n{{#- converted from {pkg.tool} task '{task.name}' -#}}\n"
                        f"{{% set sql %}}\n{task.converted_sql}\n{{% endset %}}\n{{% do run_query(sql) %}}\n{{% endmacro %}}\n")
                put(f"macros/{name}.sql", body)
    put("altitude_manifest.json", json.dumps({
        "project": project.name,
        "models": {m.name: {"layer": m.layer, "job": m.job, "tags": m.tags,
                            "tests": sum(len(c.tests) for c in m.columns)} for m in sorted(project.models.values(), key=lambda x: x.name)},
        "jobs": [a.to_dict() for a in project.assessments],
        "skipped": project.skipped,
    }, indent=2, default=str))
    return files
