"""Informatica PowerCenter XML export parser -> mapping graphs (one per MAPPING).

Reads SOURCE / TARGET definitions (fields, keys, references), folder-level reusable and mapping-level
TRANSFORMATIONs (ports, expressions, table attributes), INSTANCEs and CONNECTORs. Supports Source Qualifier,
Expression (variable ports inlined), Filter, Lookup, Aggregator, Joiner, Router, Union, Sorter, Sequence;
Mapplets, Java, Update Strategy, Stored Procedure ... become ``unsupported`` nodes with their known issue.
SESSION overrides and parameter files are attached to the mapping they run. WORKFLOWs tag the mappings
whose sessions they contain (used for scheduler -> dbt tag mapping).
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
from .graph import Column, Edge, GraphIssue, MappingGraph, Node, Output, PackageParse
from .naming import ident, table_name

TOOL = "informatica"
_DB_DIALECT = {"oracle": "oracle", "microsoft sql server": "tsql", "teradata": "teradata", "db2": "postgres",
               "odbc": "postgres", "sybase": "tsql", "netezza": "postgres"}


def _ki(g: MappingGraph, kid: str, message: str, node: str | None = None) -> None:
    g.issue(kid, kb.known_issues().get(kid, {}).get("severity", "S2"), message, node)


def _attrs(el: ET.Element) -> dict[str, str]:
    return {a.get("NAME"): a.get("VALUE", "") for a in el.findall("TABLEATTRIBUTE")}


def _ptype(port: ET.Element) -> set[str]:
    return set((port.get("PORTTYPE") or "").upper().replace(" ", "_").split("/"))


def _ftype(f: ET.Element) -> str:
    return kb.map_type(TOOL, f.get("DATATYPE", ""), f.get("LENGTH"), f.get("PRECISION"), f.get("SCALE"))


def _key(f: ET.Element) -> str | None:
    k = (f.get("KEYTYPE") or "").upper()
    if "PRIMARY" in k:
        return "primary"
    if "FOREIGN" in k:
        return "foreign"
    return None


def _columns(defn: ET.Element, tag: str) -> list[Column]:
    cols = []
    for f in defn.findall(tag):
        k = (f.get("KEYTYPE") or "").upper()
        cols.append(Column(
            name=ident(f.get("NAME")), type=_ftype(f), key=_key(f),
            ref_table=table_name(f.get("REFERENCEDTABLE")) if f.get("REFERENCEDTABLE") and "FOREIGN" in k else None,
            ref_column=ident(f.get("REFERENCEDFIELD")) if f.get("REFERENCEDFIELD") and "FOREIGN" in k else None,
            nullable=(f.get("NULLABLE") or "NULL").upper() != "NOTNULL",
            description=f.get("DESCRIPTION") or "",
        ))
    return cols


def _strip_qualifiers(sql: str, dialect: str) -> str:
    """Native source SQL predicate -> Snowflake SQL over unqualified, normalised column names."""
    tree = sqlglot.parse_one(sql, read=dialect)
    for col in tree.find_all(exp.Column):
        col.set("table", None)
        col.set("this", exp.to_identifier(ident(col.name)))
    return tree.sql(dialect="snowflake")


def _inline_variables(expr: str, variables: dict[str, str], depth: int = 0) -> str:
    """Substitute variable-port names with their (parenthesised) expressions, outside string literals."""
    if depth > len(variables) + 1:
        raise UnsupportedExpression("variable ports reference each other cyclically (row-by-row state)")
    parts = re.split(r"('(?:[^']|'')*')", expr)
    changed = False
    for i in range(0, len(parts), 2):
        for name, body in variables.items():
            new = re.sub(rf"(?<![\w$]){re.escape(name)}(?![\w$])", f"({body})", parts[i], flags=re.I)
            if new != parts[i]:
                parts[i] = new
                changed = True
    out = "".join(parts)
    return _inline_variables(out, variables, depth + 1) if changed else out


class _Folder:
    def __init__(self, folder: ET.Element, source_file: str):
        self.folder = folder
        self.source_file = source_file
        self.sources = {(s.get("DBDNAME"), s.get("NAME")): s for s in folder.findall("SOURCE")}
        self.sources_by_name = {s.get("NAME").upper(): s for s in folder.findall("SOURCE")}
        self.targets = {t.get("NAME"): t for t in folder.findall("TARGET")}
        self.reusable = {t.get("NAME"): t for t in folder.findall("TRANSFORMATION")}

    # ------------------------------------------------------------------ mapping
    def mapping(self, m: ET.Element) -> MappingGraph:
        name = m.get("NAME")
        g = MappingGraph(tool=TOOL, job=name, source_file=self.source_file, package=self.folder.get("NAME"),
                         tags=[ident(name)])
        local = {t.get("NAME"): t for t in m.findall("TRANSFORMATION")}
        instances = m.findall("INSTANCE")
        self._default_system = next((ident(i.get("DBDNAME")) for i in instances
                                     if i.get("TRANSFORMATION_TYPE") == "Source Definition" and i.get("DBDNAME")), "source")
        self._db_dialect = "oracle"
        inst_info: dict[str, dict[str, Any]] = {}
        for inst in instances:
            iname, ttype = inst.get("NAME"), inst.get("TRANSFORMATION_TYPE")
            tname = inst.get("TRANSFORMATION_NAME") or iname
            nid = ident(iname)
            entry = kb.component_for(TOOL, ttype)
            kind = entry["kind"] if entry else "unsupported"
            node = g.add(Node(nid, iname, kind, ttype))
            inst_info[iname] = {"node": node, "entry": entry}
            if entry and entry.get("known_issue") and kind == "unsupported":
                _ki(g, entry["known_issue"], f"{iname} ({ttype}): {entry['target']}", nid)
            if entry is None:
                _ki(g, "ETL-GEN-03", f"{iname}: transformation type {ttype!r} has no mapping", nid)
            try:
                if ttype == "Source Definition":
                    self._source(g, node, inst)
                elif ttype == "Target Definition":
                    self._target(node, tname)
                elif kind == "unsupported":
                    node.props["reason"] = entry["target"] if entry else f"unknown transformation {ttype}"
                else:
                    t = local.get(tname)
                    if t is None:
                        t = self.reusable.get(tname)
                    if t is None:
                        raise UnsupportedExpression(f"definition of {tname} not found in export")
                    getattr(self, f"_t_{kind}")(g, node, t, inst)
            except UnsupportedExpression as e:
                node.kind = "unsupported"
                node.props["reason"] = str(e)
                _ki(g, "ETL-GEN-03", f"{iname}: {e}", nid)
        self._connectors(g, m, inst_info)
        return g

    def _translate(self, g: MappingGraph, text: str, node: str) -> Any:
        t = translate(text, TOOL)
        g.add_domain(t.comparisons)
        if t.variables:
            _ki(g, "ETL-INF-05", f"mapping parameters {sorted(t.variables)} mapped to dbt vars", node)
            for v in t.variables:
                g.variables.setdefault(v, None)
        return t

    # ------------------------------------------------------------------ node builders
    def _source(self, g: MappingGraph, node: Node, inst: ET.Element) -> None:
        name = inst.get("TRANSFORMATION_NAME") or inst.get("NAME")
        src = self.sources.get((inst.get("DBDNAME"), name))
        if src is None:
            src = self.sources_by_name.get(name.upper())
        if src is None:
            raise UnsupportedExpression(f"source definition {name} not in export")
        self._db_dialect = _DB_DIALECT.get((src.get("DATABASETYPE") or "").lower(), "oracle")
        node.props.update(table=table_name(src.get("NAME")), raw_table=f"{src.get('OWNERNAME', '')}.{src.get('NAME')}".strip("."),
                          system=ident(src.get("DBDNAME") or "source"), columns=_columns(src, "SOURCEFIELD"),
                          db_dialect=self._db_dialect, description=src.get("DESCRIPTION") or "")

    def _target(self, node: Node, name: str) -> None:
        tgt = self.targets.get(name)
        if tgt is None:
            raise UnsupportedExpression(f"target definition {name} not in export")
        node.props.update(table=table_name(tgt.get("NAME")), raw_table=tgt.get("NAME"), system="target",
                          columns=_columns(tgt, "TARGETFIELD"), description=tgt.get("DESCRIPTION") or "")

    def _t_project(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        attrs = _attrs(t)
        ports = t.findall("TRANSFORMFIELD")
        variables = {p.get("NAME"): p.get("EXPRESSION") or "" for p in ports if "VARIABLE" in "".join(_ptype(p))}
        for vname, body in variables.items():
            if re.search(rf"(?<![\w$]){re.escape(vname)}(?![\w$])", body, re.I):
                _ki(g, "ETL-INF-06", f"{node.name}: variable port {vname} carries state across rows", node.id)
                raise UnsupportedExpression(f"variable port {vname} references its previous value")
        outputs = []
        for p in ports:
            pt = _ptype(p)
            if "OUTPUT" not in pt:
                continue
            name = ident(p.get("NAME"))
            expr = p.get("EXPRESSION")
            if "INPUT" in pt or not expr or ident(expr) == name:
                outputs.append(Output(name, None, name, name, type=_ftype(p)))
                continue
            expr = _inline_variables(expr, variables) if variables else expr
            tr = self._translate(g, expr, node.id)
            outputs.append(Output(name, expr, None, tr.sql, tr.literal_values, tr.is_aggregate, _ftype(p)))
        node.props.update(outputs=outputs, passthrough_all=False, distinct=attrs.get("Select Distinct", "NO").upper() == "YES")
        if node.tool_type in ("Source Qualifier", "Application Source Qualifier"):
            assoc = inst.findall("ASSOCIATED_SOURCE_INSTANCE")
            if len(assoc) > 1:
                _ki(g, "ETL-INF-04", f"{node.name}: homogeneous join of {len(assoc)} sources inside the qualifier", node.id)
                raise UnsupportedExpression("source qualifier joins several sources")
            for attr in ("Sql Query", "User Defined Join"):
                if attrs.get(attr, "").strip():
                    node.props["sql_override"] = attrs[attr]
                    _ki(g, "ETL-INF-04", f"{node.name}: '{attr}' override bypasses the mapping graph", node.id)
                    if "$$" in attrs[attr]:
                        _ki(g, "ETL-INF-05", f"{node.name}: override uses mapping parameters", node.id)
            flt = attrs.get("Source Filter", "").strip()
            if flt:
                try:
                    node.props["filter_sql"] = _strip_qualifiers(flt, self._db_dialect)
                except sqlglot.errors.ParseError as e:
                    raise UnsupportedExpression(f"source filter not parseable: {e}") from e

    def _t_filter(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        cond = _attrs(t).get("Filter Condition", "TRUE")
        tr = self._translate(g, cond, node.id)
        node.props.update(condition=cond, condition_sql=tr.sql)

    def _t_lookup(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        attrs = _attrs(t)
        if attrs.get("Lookup Sql Override", "").strip():
            node.props["sql_override"] = attrs["Lookup Sql Override"]
            _ki(g, "ETL-INF-04", f"{node.name}: lookup SQL override", node.id)
        if attrs.get("Dynamic Lookup Cache", "NO").upper() == "YES":
            _ki(g, "ETL-INF-02", f"{node.name}: dynamic lookup cache (insert-else-update semantics)", node.id)
            raise UnsupportedExpression("dynamic lookup cache requires incremental merge design")
        policy = attrs.get("Lookup policy on multiple match", "Use Any Value")
        if policy.lower() != "report error":
            _ki(g, "ETL-INF-02", f"{node.name}: multiple-match policy '{policy}' -> deterministic dedupe on the key", node.id)
        ports = t.findall("TRANSFORMFIELD")
        lookup_ports = {ident(p.get("NAME")) for p in ports if "LOOKUP" in _ptype(p)}
        input_ports = {ident(p.get("NAME")) for p in ports if "INPUT" in _ptype(p)}
        keys = []
        for clause in re.split(r"\s+AND\s+", attrs.get("Lookup condition", ""), flags=re.I):
            m = re.match(r"^\s*(\w+)\s*(=|<>|!=|<=|>=|<|>)\s*(\w+)\s*$", clause)
            if not m:
                continue
            if m.group(2) != "=":
                raise UnsupportedExpression(f"non-equality lookup condition {clause!r}")
            a, b = ident(m.group(1)), ident(m.group(3))
            keys.append((a, b) if a in lookup_ports else (b, a))
        if not keys or any(k[0] not in lookup_ports or k[1] not in input_ports for k in keys):
            raise UnsupportedExpression(f"lookup condition {attrs.get('Lookup condition')!r} not understood")
        returns = [(ident(p.get("NAME")), ident(p.get("NAME"))) for p in ports
                   if "LOOKUP" in _ptype(p) and "OUTPUT" in _ptype(p)]
        passthrough = [ident(p.get("NAME")) for p in ports if {"INPUT", "OUTPUT"} <= _ptype(p) and "LOOKUP" not in _ptype(p)]
        table = attrs.get("Lookup table name") or t.get("NAME")
        conn = attrs.get("Connection Information", "$Source")
        system = self._default_system if conn.startswith("$") else ident(conn.split(".")[-1])
        src = self.sources_by_name.get(table.upper())
        lookup_cols = _columns(src, "SOURCEFIELD") if src is not None else [
            Column(ident(p.get("NAME")), _ftype(p)) for p in ports if "LOOKUP" in _ptype(p)]
        node.props.update(table=table_name(table), raw_table=table, system=system, keys=keys, returns=returns,
                          passthrough=passthrough, lookup_columns=lookup_cols, join="left", policy=policy)

    def _t_aggregate(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        group_by, outputs = [], []
        for p in t.findall("TRANSFORMFIELD"):
            pt = _ptype(p)
            name = ident(p.get("NAME"))
            is_group = (p.get("EXPRESSIONTYPE") or "").upper() == "GROUPBY" or (p.get("GROUPBY") or "").upper() == "YES"
            if is_group:
                group_by.append(name)
            if "OUTPUT" not in pt:
                continue
            expr = p.get("EXPRESSION")
            if is_group:
                outputs.append(Output(name, None, name, name, type=_ftype(p)))
            elif "INPUT" in pt and (not expr or ident(expr) == name):
                _ki(g, "ETL-INF-06", f"{node.name}: non-aggregated port {p.get('NAME')} returns the last row; ANY_VALUE used", node.id)
                outputs.append(Output(name, f"ANY_VALUE({name})", None, f"ANY_VALUE({name})", None, True, _ftype(p),
                                      expr_is_sql=True))
            else:
                tr = self._translate(g, expr, node.id)
                if not tr.is_aggregate:
                    raise UnsupportedExpression(f"aggregator output {p.get('NAME')} is not an aggregate")
                outputs.append(Output(name, expr, None, tr.sql, None, True, _ftype(p)))
        if not group_by:
            _ki(g, "ETL-INF-06", f"{node.name}: aggregator without group-by returns one row", node.id)
        node.props.update(group_by=group_by, outputs=outputs)

    def _t_join(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        attrs = _attrs(t)
        ports = t.findall("TRANSFORMFIELD")
        master = {ident(p.get("NAME")) for p in ports if "MASTER" in _ptype(p)}
        conds = []
        for clause in re.split(r"\s+AND\s+", attrs.get("Join Condition", ""), flags=re.I):
            m = re.match(r"^\s*(\w+)\s*=\s*(\w+)\s*$", clause)
            if not m:
                raise UnsupportedExpression(f"join condition {clause!r} not supported")
            a, b = ident(m.group(1)), ident(m.group(2))
            conds.append((a, b) if a in master else (b, a))
        jt = kb.components(TOOL).get("join_types", {}).get(attrs.get("Join Type", "Normal Join"))
        if jt is None:
            raise UnsupportedExpression(f"join type {attrs.get('Join Type')!r} not mapped")
        outputs = [(ident(p.get("NAME")), "master" if "MASTER" in _ptype(p) else "detail")
                   for p in ports if "OUTPUT" in _ptype(p)]
        node.props.update(join_type=jt, conditions=conds, outputs=outputs, master_ports=sorted(master))

    def _t_split(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        groups, default, group_fields = [], None, {}
        for grp in t.findall("GROUP"):
            gtype = (grp.get("TYPE") or "").upper()
            if gtype == "OUTPUT":
                self._translate(g, grp.get("EXPRESSION") or "TRUE", node.id)
                groups.append((grp.get("NAME"), grp.get("EXPRESSION") or "TRUE"))
            elif "DEFAULT" in gtype:
                default = grp.get("NAME")
        for p in t.findall("TRANSFORMFIELD"):
            gname = p.get("GROUP")
            if gname and gname != "INPUT" and p.get("REF_FIELD"):
                group_fields.setdefault(gname, []).append((ident(p.get("REF_FIELD")), ident(p.get("NAME"))))
        node.props.update(groups=groups, default_group=default, semantics="all_match", group_fields=group_fields)

    def _t_union(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        outs = [ident(p.get("NAME")) for p in t.findall("TRANSFORMFIELD") if "OUTPUT" in _ptype(p)]
        node.props.update(columns=outs)

    def _t_sort(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        node.props["distinct"] = _attrs(t).get("Distinct", "NO").upper() == "YES"

    def _t_sequence(self, g: MappingGraph, node: Node, t: ET.Element, inst: ET.Element) -> None:
        attrs = _attrs(t)
        node.props.update(start=int(attrs.get("Start Value", "1") or 1), field="nextval")

    # ------------------------------------------------------------------ connectors
    def _connectors(self, g: MappingGraph, m: ET.Element, info: dict[str, dict]) -> None:
        groups: dict[tuple[str, str, str | None, str | None], list[tuple[str, str]]] = {}
        for c in m.findall("CONNECTOR"):
            fi, ti = c.get("FROMINSTANCE"), c.get("TOINSTANCE")
            if fi not in info or ti not in info:
                continue
            src, dst = info[fi]["node"], info[ti]["node"]
            ff, tf = ident(c.get("FROMFIELD")), ident(c.get("TOFIELD"))
            port = None
            if src.kind == "split":
                port = next((gname for gname, flds in (src.props.get("group_fields") or {}).items()
                             if any(out == ff for _, out in flds)), None)
            role = None
            if dst.kind == "join":
                role = "master" if tf in set(dst.props.get("master_ports", [])) else "detail"
            groups.setdefault((src.id, dst.id, port, role), []).append((ff, tf))
        for (src, dst, port, role), fields in groups.items():
            g.connect(Edge(src, dst, fields, port, role))


def parse_powercenter(path: str | Path) -> list[PackageParse]:
    """Parse a PowerCenter XML export; one :class:`PackageParse` per FOLDER."""
    path = Path(path)
    root = ET.parse(path).getroot()
    out = []
    for folder in root.iter("FOLDER"):
        f = _Folder(folder, path.name)
        pkg = PackageParse(tool=TOOL, package=folder.get("NAME"), source_file=path.name)
        graphs = {m.get("NAME"): f.mapping(m) for m in folder.findall("MAPPING")}
        for sess in folder.findall("SESSION"):
            g = graphs.get(sess.get("MAPPINGNAME"))
            if g is None:
                continue
            for sti in sess.findall("SESSTRANSFORMATIONINST"):
                for attr in sti.findall("ATTRIBUTE"):
                    if attr.get("NAME") in ("Sql Query", "Lookup Sql Override", "Source Filter") and attr.get("VALUE", "").strip():
                        _ki(g, "ETL-INF-04", f"session {sess.get('NAME')} overrides {attr.get('NAME')} on "
                                             f"{sti.get('SINSTANCENAME')}", ident(sti.get("SINSTANCENAME") or ""))
                        node = g.nodes.get(ident(sti.get("SINSTANCENAME") or ""))
                        if node is not None:
                            node.props["sql_override"] = attr.get("VALUE")
            for attr in sess.findall("ATTRIBUTE"):
                if attr.get("NAME") == "Parameter Filename" and attr.get("VALUE"):
                    _ki(g, "ETL-INF-05", f"session {sess.get('NAME')} reads parameter file {attr.get('VALUE')}")
        session_to_mapping = {s.get("NAME"): s.get("MAPPINGNAME") for s in folder.findall("SESSION")}
        for wf in folder.findall("WORKFLOW"):
            for ti in wf.findall("TASKINSTANCE"):
                mapping = session_to_mapping.get(ti.get("TASKNAME"))
                if mapping in graphs and ident(wf.get("NAME")) not in graphs[mapping].tags:
                    graphs[mapping].tags.append(ident(wf.get("NAME")))
        pkg.graphs = list(graphs.values())
        out.append(pkg)
    return out
