"""SSIS ``.dtsx`` parser (package format 2012+) -> mapping graphs + control-flow tasks.

Data flows (``Microsoft.Pipeline``) become :class:`MappingGraph` jobs: connection managers, sources,
derived columns, data conversions, lookups, conditional splits, union all, sorts, aggregates and
destinations. Execute SQL tasks are transpiled (T-SQL -> Snowflake) and classified; script tasks, script
components and event handlers are flagged for re-engineering. Component semantics come from
``knowledge/etl/components_ssis.yaml``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

from . import kb
from .expr import UnsupportedExpression, translate
from .graph import Column, ControlTask, Edge, GraphIssue, MappingGraph, Node, Output, PackageParse
from .naming import ident, qualified_table, table_name

DTS = "www.microsoft.com/SqlServer/Dts"
SQLTASK = "www.microsoft.com/sqlserver/dts/tasks/sqltask"
TOOL = "ssis"
# DTS:DataType of package variables -> dbt var SQL type
_VAR_TYPES = {"2": "number", "3": "number", "4": "number", "5": "number", "6": "number", "14": "number",
              "16": "number", "17": "number", "18": "number", "19": "number", "20": "number", "21": "number",
              "7": "timestamp", "11": "boolean", "8": "string"}
_AGG = {"0": None, "1": "COUNT({0})", "2": "COUNT(*)", "3": "COUNT(DISTINCT {0})", "4": "SUM({0})",
        "5": "AVG({0})", "6": "MIN({0})", "7": "MAX({0})"}


def _a(el: ET.Element, name: str, default: str | None = None) -> str | None:
    v = el.get(f"{{{DTS}}}{name}")
    if v is None:
        v = el.get(name)
    return default if v is None else v


def _props(el: ET.Element) -> dict[str, str]:
    box = el.find("properties")
    if box is None:
        return {}
    return {p.get("name"): (p.text or "") for p in box.findall("property")}


def _issue(kid: str, message: str, node: str | None = None) -> GraphIssue:
    ki = kb.known_issues().get(kid, {})
    return GraphIssue(kid, ki.get("severity", "S2"), node, message)


def _bracket(ref: str, kind: str) -> tuple[str, str] | None:
    """``Package\\DFT\\Comp.Outputs[Name]`` -> (``Package\\DFT\\Comp``, ``Name``)."""
    m = re.match(rf"^(.*)\.{kind}\[(.*)\]$", ref or "")
    return (m.group(1), m.group(2)) if m else None


def _col_type(el: ET.Element, prefix: str = "") -> str:
    dt = el.get(prefix + "dataType") or el.get(prefix + "DataType") or ""
    return kb.map_type(TOOL, dt, el.get(prefix + "length"), el.get(prefix + "precision"), el.get(prefix + "scale"))


def _table_from_sql(sql: str) -> tuple[str | None, bool]:
    """Single-table SELECT -> (table, simple). Anything else -> (first table, False)."""
    try:
        tree = sqlglot.parse_one(sql, read="tsql")
    except sqlglot.errors.ParseError:
        return None, False
    tables = list(tree.find_all(exp.Table))
    simple = (isinstance(tree, exp.Select) and len(tables) == 1 and not tree.args.get("joins")
              and not tree.args.get("where") and not tree.args.get("group") and not tree.args.get("distinct"))
    return (".".join(p for p in (tables[0].db, tables[0].name) if p) if tables else None), simple


class _DataFlow:
    def __init__(self, pkg: PackageParse, el: ET.Element, name: str, conns: dict[str, str]):
        self.pkg = pkg
        self.el = el
        self.conns = conns
        self.g = MappingGraph(tool=TOOL, job=f"{pkg.package}::{name}", source_file=pkg.source_file,
                              package=pkg.package, variables=dict(pkg.variables), var_types=dict(pkg.var_types),
                              tags=[ident(pkg.package)])
        self.ref_to_node: dict[str, str] = {}

    def _translate(self, text: str, node: str) -> Any:
        t = translate(text, TOOL, var_types=self.g.var_types)
        self.g.add_domain(t.comparisons)
        if t.variables:
            self.g.issue("ETL-SSIS-03", "S2", f"package variables {sorted(t.variables)} mapped to dbt vars", node)
        return t

    def _system(self, comp: ET.Element) -> str:
        c = comp.find("connections/connection")
        if c is None:
            return "default"
        ref = c.get("connectionManagerRefId") or c.get("connectionManagerID") or ""
        return ident(self.conns.get(ref, ref.split("[")[-1].rstrip("]") or "default"))

    def parse(self) -> MappingGraph:
        pipeline = self.el.find(f"{{{DTS}}}ObjectData/pipeline")
        if pipeline is None:
            return self.g
        for comp in pipeline.findall("components/component"):
            self._component(comp)
        for path in pipeline.findall("paths/path"):
            start = _bracket(path.get("startId", ""), "Outputs")
            end = _bracket(path.get("endId", ""), "Inputs")
            if not start or not end or start[0] not in self.ref_to_node or end[0] not in self.ref_to_node:
                continue
            src, dst = self.ref_to_node[start[0]], self.ref_to_node[end[0]]
            src_node, dst_node = self.g.nodes[src], self.g.nodes[dst]
            port = start[1] if src_node.kind == "split" else None
            if src_node.kind == "lookup" and "no match" in start[1].lower():
                src_node.props["join"] = "left"
                self.g.issue("ETL-SSIS-04", "S1", "lookup no-match rows are routed downstream: modelled as LEFT JOIN", src)
                port = None
                if any(e.src == src and e.dst == dst for e in self.g.edges):
                    continue
            fields = dst_node.props.pop("_pending_fields", None) if dst_node.kind == "target" else None
            self.g.connect(Edge(src, dst, fields, port, end[1] if dst_node.kind in ("union", "join") else None))
        return self.g

    # ------------------------------------------------------------------ components
    def _component(self, comp: ET.Element) -> None:
        cls = comp.get("componentClassID", "")
        name = comp.get("name", "component")
        nid = ident(name)
        entry = kb.component_for(TOOL, cls)
        kind = entry["kind"] if entry else "unsupported"
        self.ref_to_node[comp.get("refId") or f"Package\\{name}"] = nid
        node = self.g.add(Node(nid, name, kind if kind != "passthrough" else "project", cls))
        if entry and entry.get("known_issue"):
            ki = entry["known_issue"]
            self.g.issue(ki, kb.known_issues().get(ki, {}).get("severity", "S2"),
                         f"{name}: {entry['target']}", nid)
        if entry is None:
            self.g.issue("ETL-GEN-03", "S2", f"unknown component class {cls!r}", nid)
        props = _props(comp)
        try:
            handler = getattr(self, f"_c_{node.kind}", None)
            if node.kind == "project" and kind == "passthrough":
                node.props.update(outputs=[], passthrough_all=True)
            elif handler:
                handler(node, comp, props)
            if node.kind == "unsupported":
                node.props["reason"] = entry["target"] if entry else f"unknown component {cls}"
        except UnsupportedExpression as e:
            node.kind = "unsupported"
            node.props["reason"] = str(e)
            self.g.issue("ETL-GEN-03", "S2", f"{name}: {e}", nid)

    def _c_source(self, node: Node, comp: ET.Element, props: dict) -> None:
        out = next((o for o in comp.findall("outputs/output") if o.get("isErrorOut") != "true"), None)
        cols = [Column(ident(c.get("name")), _col_type(c)) for c in (out.findall("outputColumns/outputColumn") if out is not None else [])]
        access = props.get("AccessMode", "0")
        table = props.get("OpenRowset") or ""
        sql = props.get("SqlCommand") or ""
        if access in ("2",) or (not table and sql):
            tbl, simple = _table_from_sql(sql)
            table = tbl or node.name
            if not simple:
                node.props["sql_override"] = sql
                self.g.issue("ETL-GEN-04", "S3", f"{node.name}: source SQL command is not a single-table select", node.id)
        node.props.update(table=qualified_table(table), raw_table=table, system=self._system(comp), columns=cols)
        if comp.get("componentClassID", "").endswith(("FlatFileSource", "ExcelSource")):
            node.props["file_based"] = True

    def _c_target(self, node: Node, comp: ET.Element, props: dict) -> None:
        inp = comp.find("inputs/input")
        ext = {}
        cols = []
        if inp is not None:
            for e in inp.findall("externalMetadataColumns/externalMetadataColumn"):
                ext[e.get("refId") or e.get("name")] = e.get("name")
                cols.append(Column(ident(e.get("name")), _col_type(e)))
            fields = []
            for ic in inp.findall("inputColumns/inputColumn"):
                ref = ic.get("externalMetadataColumnId") or ""
                target = ext.get(ref) or (_bracket(ref, "ExternalColumns") or (None, ic.get("cachedName")))[1]
                fields.append((ident(ic.get("cachedName")), ident(target)))
            node.props["_pending_fields"] = fields
        table = props.get("OpenRowset") or props.get("SqlCommand") or node.name
        node.props.update(table=qualified_table(table), raw_table=table, system=self._system(comp), columns=cols)

    def _c_project(self, node: Node, comp: ET.Element, props: dict) -> None:
        outputs: list[Output] = []
        for ic in comp.findall("inputs/input/inputColumns/inputColumn"):
            p = _props(ic)
            expr = p.get("FriendlyExpression") or p.get("Expression")
            if ic.get("usageType") == "readWrite" and expr:
                t = self._translate(expr, node.id)
                outputs.append(Output(ident(ic.get("cachedName")), expr, None, t.sql, t.literal_values,
                                      t.is_aggregate, kb.map_type(TOOL, ic.get("cachedDataType", ""),
                                                                  ic.get("cachedLength"), ic.get("cachedPrecision"),
                                                                  ic.get("cachedScale"))))
        cls = comp.get("componentClassID", "")
        for out in comp.findall("outputs/output"):
            if out.get("isErrorOut") == "true":
                continue
            for oc in out.findall("outputColumns/outputColumn"):
                p = _props(oc)
                expr = p.get("FriendlyExpression") or p.get("Expression")
                if cls.endswith("DataConvert"):
                    src = p.get("SourceInputColumnLineageID", "")
                    col = (_bracket(src, "Columns") or (None, ""))[1] or oc.get("name").replace("Copy of ", "")
                    expr = f"(DT_WSTR,{oc.get('length') or 255}){col}" if "str" in (oc.get("dataType") or "") else None
                    if expr is None:
                        outputs.append(Output(ident(oc.get("name")), None, ident(col), ident(col), type=_col_type(oc)))
                        continue
                if not expr:
                    continue
                t = self._translate(expr, node.id)
                outputs.append(Output(ident(oc.get("name")), expr, None, t.sql, t.literal_values, t.is_aggregate,
                                      _col_type(oc)))
        node.props.update(outputs=outputs, passthrough_all=True)

    def _c_lookup(self, node: Node, comp: ET.Element, props: dict) -> None:
        sql = props.get("SqlCommand") or ""
        table, simple = _table_from_sql(sql) if sql else (None, False)
        if not table:
            table = node.name
        if sql and not simple:
            # a projection-only SELECT is fine; filters/joins in the reference query change semantics
            try:
                tree = sqlglot.parse_one(sql, read="tsql")
                simple = not (tree.args.get("where") or tree.args.get("joins") or tree.args.get("group"))
            except sqlglot.errors.ParseError:
                simple = False
            if not simple:
                node.props["sql_override"] = sql
                self.g.issue("ETL-GEN-04", "S3", f"{node.name}: lookup reference query is not a plain table read", node.id)
        keys, lookup_cols = [], []
        for ic in comp.findall("inputs/input/inputColumns/inputColumn"):
            ref = _props(ic).get("JoinToReferenceColumn")
            if ref:
                keys.append((ident(ref), ident(ic.get("cachedName"))))
                lookup_cols.append(Column(ident(ref), kb.map_type(TOOL, ic.get("cachedDataType", ""), ic.get("cachedLength"))))
        returns = []
        for out in comp.findall("outputs/output"):
            if out.get("isErrorOut") == "true" or "no match" in (out.get("name") or "").lower():
                continue
            for oc in out.findall("outputColumns/outputColumn"):
                ref = _props(oc).get("CopyFromReferenceColumn") or oc.get("name")
                returns.append((ident(oc.get("name")), ident(ref)))
                lookup_cols.append(Column(ident(ref), _col_type(oc)))
        if not keys:
            raise UnsupportedExpression(f"lookup {node.name} has no join columns")
        no_match = props.get("NoMatchBehavior", "0")
        node.props.update(table=qualified_table(table), raw_table=table, system=self._system(comp), keys=keys,
                          returns=returns, passthrough=None, lookup_columns=lookup_cols,
                          join="inner", policy="cache" if props.get("CacheType", "0") == "0" else "partial",
                          no_match_behavior=no_match)

    def _c_split(self, node: Node, comp: ET.Element, props: dict) -> None:
        groups, default = [], None
        for out in comp.findall("outputs/output"):
            if out.get("isErrorOut") == "true":
                continue
            p = _props(out)
            if p.get("IsDefaultOut", "false").lower() == "true":
                default = out.get("name")
                continue
            expr = p.get("FriendlyExpression") or p.get("Expression")
            self._translate(expr, node.id)
            groups.append((int(p.get("EvaluationOrder", len(groups))), out.get("name"), expr))
        groups.sort()
        node.props.update(groups=[(n, e) for _, n, e in groups], default_group=default, semantics="first_match",
                          group_fields=None)

    def _c_union(self, node: Node, comp: ET.Element, props: dict) -> None:
        out = comp.find("outputs/output")
        cols = [ident(c.get("name")) for c in out.findall("outputColumns/outputColumn")] if out is not None else []
        node.props.update(columns=cols or None)

    def _c_sort(self, node: Node, comp: ET.Element, props: dict) -> None:
        node.props["distinct"] = props.get("EliminateDuplicates", "false").lower() == "true"

    def _c_aggregate(self, node: Node, comp: ET.Element, props: dict) -> None:
        inputs = {}
        for ic in comp.findall("inputs/input/inputColumns/inputColumn"):
            for key in (ic.get("refId"), ic.get("lineageId"), ic.get("cachedName")):
                if key:
                    inputs[key] = ident(ic.get("cachedName"))
        group_by, outputs = [], []
        for out in comp.findall("outputs/output"):
            if out.get("isErrorOut") == "true":
                continue
            for oc in out.findall("outputColumns/outputColumn"):
                p = _props(oc)
                agg = p.get("AggregationType", "0")
                src = inputs.get(p.get("AggregationColumnId", "")) or inputs.get(oc.get("name")) or ident(oc.get("name"))
                name = ident(oc.get("name"))
                if agg not in _AGG:
                    raise UnsupportedExpression(f"aggregation type {agg} not mapped")
                if _AGG[agg] is None:
                    group_by.append(src)
                    outputs.append(Output(name, None, src, src, type=_col_type(oc)))
                else:
                    sql = _AGG[agg].format(src)
                    outputs.append(Output(name, sql, None, sql, None, True, _col_type(oc), expr_is_sql=True))
        node.props.update(group_by=group_by, outputs=outputs)

    def _c_join(self, node: Node, comp: ET.Element, props: dict) -> None:
        raise UnsupportedExpression("Merge Join key mapping requires sorted-input metadata; re-engineer as a model join")


# --------------------------------------------------------------------------- package


def parse_dtsx(path: str | Path) -> PackageParse:
    path = Path(path)
    root = ET.parse(path).getroot()
    package = _a(root, "ObjectName") or path.stem
    pkg = PackageParse(tool=TOOL, package=package, source_file=path.name)
    conns: dict[str, str] = {}
    for cm in root.iter(f"{{{DTS}}}ConnectionManager"):
        name = _a(cm, "ObjectName")
        if not name:
            continue
        for key in (_a(cm, "refId"), _a(cm, "DTSID")):
            if key:
                conns[key] = name
    for var in root.findall(f"{{{DTS}}}Variables/{{{DTS}}}Variable"):
        name = ident(_a(var, "ObjectName") or "var")
        val = var.find(f"{{{DTS}}}VariableValue")
        if val is not None:
            pkg.variables[name] = val.text or ""
            pkg.var_types[name] = _VAR_TYPES.get(_a(val, "DataType") or "8", "string")
    if root.find(f"{{{DTS}}}Configurations") is not None:
        pkg.issues.append(_issue("ETL-SSIS-03", "package configurations must be mapped to environment config"))
    targets_by_flow: set[str] = set()
    for ex in _executables(root):
        _executable(pkg, ex, conns)
    for g in pkg.graphs:
        targets_by_flow |= {n.props.get("table") for n in g.by_kind("target")}
    for task in pkg.control_tasks:
        if task.kind == "sql_task" and task.sql:
            m = re.match(r"^\s*TRUNCATE\s+TABLE\s+([\w.\[\]]+)\s*;?\s*$", task.sql, re.I)
            if m and table_name(m.group(1)) in targets_by_flow:
                task.recommendation_hint = "retire"
                task.note = "truncate before a full reload is redundant: the dbt model is materialised as a table"
    for pc in root.findall(f"{{{DTS}}}PrecedenceConstraints/{{{DTS}}}PrecedenceConstraint"):
        pkg.precedence.append((_short(_a(pc, "From")), _short(_a(pc, "To"))))
    for eh in root.findall(f"{{{DTS}}}EventHandlers/{{{DTS}}}EventHandler"):
        name = _a(eh, "EventName") or _a(eh, "ObjectName") or "EventHandler"
        inner = [(_a(e, "ObjectName") or "") for e in eh.iter(f"{{{DTS}}}Executable")]
        pkg.control_tasks.append(ControlTask(
            name=f"EventHandler[{name}]", kind="event_handler", tool_type="DTS:EventHandler",
            issues=[_issue("ETL-SSIS-02", f"{name} handler ({', '.join(inner) or 'empty'}) moves to orchestrator callbacks")],
            recommendation_hint="re-engineer"))
    return pkg


def _short(ref: str | None) -> str:
    return (ref or "").split("\\")[-1]


def _executables(el: ET.Element):
    box = el.find(f"{{{DTS}}}Executables")
    if box is None:
        return
    for ex in box.findall(f"{{{DTS}}}Executable"):
        yield ex
        yield from _executables(ex)


def _executable(pkg: PackageParse, ex: ET.Element, conns: dict[str, str]) -> None:
    etype = _a(ex, "ExecutableType") or _a(ex, "CreationName") or ""
    name = _a(ex, "ObjectName") or "task"
    entry = kb.component_for(TOOL, etype)
    kind = entry["kind"] if entry else "unknown"
    if kind == "data_flow":
        pkg.graphs.append(_DataFlow(pkg, ex, name, conns).parse())
        return
    task = ControlTask(name=name, kind=kind, tool_type=etype)
    if kind == "sql_task":
        data = ex.find(f"{{{DTS}}}ObjectData/{{{SQLTASK}}}SqlTaskData")
        sql = (data.get(f"{{{SQLTASK}}}SqlStatementSource") if data is not None else "") or ""
        task.sql = sql
        try:
            task.converted_sql = ";\n".join(sqlglot.transpile(sql, read="tsql", write="snowflake",
                                                              unsupported_level=sqlglot.ErrorLevel.RAISE)) + ";"
            task.recommendation_hint = "lift"
        except (sqlglot.errors.ParseError, sqlglot.errors.UnsupportedError) as e:
            task.issues.append(_issue("ETL-GEN-04", f"{name}: {str(e).splitlines()[0]}"))
            task.recommendation_hint = "re-engineer"
        task.target_tables = [table_name(t.name) for t in _tables(sql)]
    elif kind == "script_task":
        task.issues.append(_issue("ETL-SSIS-01", f"{name}: script task code must be re-engineered"))
        task.recommendation_hint = "re-engineer"
    elif kind in ("container",):
        if "FOREACH" in etype.upper():
            task.issues.append(_issue("ETL-GEN-02", f"{name}: Foreach loop (often file enumeration)"))
        task.recommendation_hint = "lift"
    elif kind == "file_task":
        task.issues.append(_issue("ETL-GEN-02", f"{name}: file-system / FTP side effects"))
        task.recommendation_hint = "re-engineer"
    elif kind == "unknown":
        task.issues.append(_issue("ETL-GEN-03", f"{name}: unknown executable type {etype}"))
        task.recommendation_hint = "re-engineer"
    else:
        task.recommendation_hint = "lift"
    if entry:
        task.note = entry["target"]
    pkg.control_tasks.append(task)


def _tables(sql: str) -> list[exp.Table]:
    try:
        return [t for tree in sqlglot.parse(sql, read="tsql") if tree for t in tree.find_all(exp.Table)]
    except sqlglot.errors.ParseError:
        return []
