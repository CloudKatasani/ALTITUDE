"""Common mapping graph: the tool-neutral representation SSIS and Informatica parsers produce.

Nodes are transformation steps with a ``kind`` (source, project, filter, lookup, aggregate, join, split,
union, sort, sequence, passthrough, target, unsupported). Column names are already normalised
(``naming.ident``) and expressions already translated to Snowflake SQL. Edges carry field mappings
(``(from_field, to_field)``; ``None`` = all columns by name) and optional ports (router/split group on the
source side, join role on the destination side).

Node ``props`` by kind:
- source:    table, system, schema, columns: [Column]
- project:   outputs: [Output], passthrough_all: bool, filter: expr|None, filter_sql: sql|None, distinct: bool
- filter:    condition: expr
- lookup:    table, system, keys: [(lookup_col, input_col)], returns: [(out_name, lookup_col)],
             passthrough: [names]|None, lookup_columns: [Column], join: left|inner, policy
- aggregate: group_by: [names], outputs: [Output]
- join:      join_type, conditions: [(master_field, detail_field)], outputs: [names]
- split:     groups: [(name, condition expr)], default_group, semantics: first_match|all_match,
             group_fields: {group: [(in, out)]} | None
- union:     columns: [names] | None
- sort:      distinct: bool
- sequence:  start: int, field: str
- target:    table, system, columns: [Column]
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any

from altitude.core.ids import content_hash


@dataclass
class Column:
    name: str
    type: str = "VARCHAR"
    key: str | None = None          # primary|foreign
    ref_table: str | None = None
    ref_column: str | None = None
    nullable: bool = True
    description: str = ""


@dataclass
class Output:
    """One output column. ``expr`` is the tool expression (None = passthrough of input ``source``)."""

    name: str
    expr: str | None = None
    source: str | None = None
    sql: str = ""                       # translation with identity column resolution (documentation)
    literal_values: list[str] | None = None
    is_aggregate: bool = False
    type: str = "VARCHAR"
    expr_is_sql: bool = False           # expr is already SQL over the node's input columns

    @property
    def is_passthrough(self) -> bool:
        return self.expr is None


@dataclass
class Node:
    id: str
    name: str
    kind: str
    tool_type: str
    props: dict[str, Any] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)


@dataclass
class Edge:
    src: str
    dst: str
    fields: list[tuple[str, str]] | None = None
    src_port: str | None = None
    dst_port: str | None = None


@dataclass
class GraphIssue:
    id: str            # known issue id (knowledge/etl/known_issues.yaml)
    severity: str      # S1..S4
    node: str | None
    message: str


@dataclass
class MappingGraph:
    tool: str
    job: str
    source_file: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    issues: list[GraphIssue] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    control_tasks: list[dict[str, Any]] = field(default_factory=list)
    package: str = ""
    tags: list[str] = field(default_factory=list)
    domains: dict[str, list[str]] = field(default_factory=dict)   # column -> literal values seen in logic
    var_types: dict[str, str] = field(default_factory=dict)

    def add_domain(self, pairs: list[tuple[str, str]]) -> None:
        for col, value in pairs:
            vals = self.domains.setdefault(col, [])
            if value not in vals:
                vals.append(value)

    # ------------------------------------------------------------------ building
    def add(self, node: Node) -> Node:
        if node.id in self.nodes:
            raise ValueError(f"duplicate node id {node.id}")
        self.nodes[node.id] = node
        return node

    def connect(self, edge: Edge) -> None:
        self.edges.append(edge)

    def issue(self, known_id: str, severity: str, message: str, node: str | None = None) -> None:
        gi = GraphIssue(known_id, severity, node, message)
        if gi not in self.issues:
            self.issues.append(gi)
        if node and node in self.nodes and known_id not in self.nodes[node].issues:
            self.nodes[node].issues.append(known_id)

    # ------------------------------------------------------------------ queries
    def inputs(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.dst == node_id]

    def outputs(self, node_id: str) -> list[Edge]:
        return [e for e in self.edges if e.src == node_id]

    def by_kind(self, *kinds: str) -> list[Node]:
        return [n for n in self.nodes.values() if n.kind in kinds]

    def topo_order(self) -> list[str]:
        indeg = {n: 0 for n in self.nodes}
        adj = defaultdict(list)
        for e in self.edges:
            adj[e.src].append(e.dst)
            indeg[e.dst] += 1
        queue = deque(sorted(n for n, d in indeg.items() if d == 0))
        order = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for m in sorted(adj[n]):
                indeg[m] -= 1
                if indeg[m] == 0:
                    queue.append(m)
        if len(order) != len(self.nodes):
            raise ValueError(f"{self.job}: mapping graph has a cycle")
        return order

    def ancestors(self, node_id: str) -> set[str]:
        seen: set[str] = set()
        stack = [node_id]
        while stack:
            n = stack.pop()
            for e in self.inputs(n):
                if e.src not in seen:
                    seen.add(e.src)
                    stack.append(e.src)
        return seen

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool, "job": self.job, "package": self.package, "source_file": self.source_file,
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
            "issues": [asdict(i) for i in self.issues],
            "variables": self.variables,
            "control_tasks": self.control_tasks,
            "tags": self.tags,
            "domains": self.domains,
        }

    def hash(self) -> str:
        d = self.to_dict()
        d.pop("source_file")
        return content_hash(d)


@dataclass
class ControlTask:
    """A control-flow step that is not a data flow (SQL task, script task, event handler, session ...)."""

    name: str
    kind: str                 # sql_task|script_task|event_handler|container|package_call|notification|file_task
    tool_type: str
    sql: str | None = None
    converted_sql: str | None = None
    target_tables: list[str] = field(default_factory=list)
    issues: list[GraphIssue] = field(default_factory=list)
    recommendation_hint: str | None = None   # retire|lift|re-engineer (parser-level evidence)
    note: str = ""


@dataclass
class PackageParse:
    """Everything parsed from one ETL export file (an SSIS package or an Informatica folder)."""

    tool: str
    package: str
    source_file: str
    graphs: list[MappingGraph] = field(default_factory=list)
    control_tasks: list[ControlTask] = field(default_factory=list)
    precedence: list[tuple[str, str]] = field(default_factory=list)
    issues: list[GraphIssue] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    var_types: dict[str, str] = field(default_factory=dict)
