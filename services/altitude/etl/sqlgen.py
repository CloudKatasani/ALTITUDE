"""Mapping graph -> Snowflake SQL (one SELECT per target, built from CTEs).

*Active* steps (sources, filters, aggregates, joins, unions, splits, distinct sorts, inner lookups,
qualifiers with filters) change the row set and become CTEs. *Passive* steps (expressions, derived columns,
connected left lookups, sequences) keep rows 1:1, so they are collapsed into column expressions over the
nearest active relation (aliased ``src``) plus LEFT JOINs to deduplicated lookup references. This is what
makes Informatica's row-aligned branches (a lookup and an expression both fed by the same qualifier and
merged again downstream) expressible as a single set-based SELECT.

Split semantics are explicit: SSIS Conditional Split is first-match (each output excludes rows matched by
earlier outputs), Informatica Router is all-match (a row reaches every group whose condition is true).
NULL conditions count as false in both.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .expr import UnsupportedExpression, translate
from .graph import Edge, MappingGraph, Node
from .naming import ident

SEQ = "__ALTITUDE_SEQ__"


class GenerationError(ValueError):
    """The graph (or part of it) cannot be generated as SQL."""


@dataclass(frozen=True)
class ColExpr:
    sql: str
    base: str | None                 # CTE name of the active relation this expression is over
    lookups: tuple[str, ...] = ()    # lookup node ids whose joins it needs
    seq_start: int | None = None     # sequence generator column


@dataclass
class _LookupJoin:
    ref_cte: str
    alias: str
    condition: str
    deps: tuple[str, ...]


@dataclass
class TargetSQL:
    target_id: str
    sql: str
    columns: list[str]
    ctes: list[str] = field(default_factory=list)


def _list(items: list[str]) -> str:
    return ",\n".join(items)


def _indent(sql: str, n: int = 4) -> str:
    return "\n".join((" " * n + ln) if ln.strip() else ln for ln in sql.splitlines())


class SqlBuilder:
    def __init__(self, graph: MappingGraph, relation_for: Callable[[Node], str]):
        """``relation_for(node)`` returns the dbt relation (``{{ ref('...') }}``) for a source or lookup table."""
        self.g = graph
        self.relation_for = relation_for
        self.ctes: dict[str, str] = {}
        self.columns: dict[str, list[str]] = {}       # CTE -> output column names
        self.lookup_joins: dict[str, _LookupJoin] = {}
        self._exprs: dict[tuple[str, str | None], dict[str, ColExpr]] = {}
        self._order = {n: i for i, n in enumerate(graph.topo_order())}

    # ------------------------------------------------------------------ classification helpers
    def is_active(self, n: Node) -> bool:
        if n.kind in ("source", "filter", "aggregate", "join", "union", "split"):
            return True
        if n.kind == "sort":
            return bool(n.props.get("distinct"))
        if n.kind == "project":
            return bool(n.props.get("filter") or n.props.get("filter_sql") or n.props.get("distinct"))
        if n.kind == "lookup":
            return n.props.get("join", "left") == "inner"
        return False

    def _translate(self, text: str, resolve: Callable[[str], str] | None) -> tuple[str, set[str]]:
        try:
            t = translate(text, self.g.tool, resolve=resolve, var_types=self.g.var_types)
        except (UnsupportedExpression, KeyError) as e:
            raise GenerationError(f"{self.g.job}: expression {text!r}: {e}") from e
        return t.sql, t.columns

    # ------------------------------------------------------------------ expressions
    def exprs(self, node_id: str, port: str | None = None) -> dict[str, ColExpr]:
        key = (node_id, port)
        if key in self._exprs:
            return self._exprs[key]
        n = self.g.nodes[node_id]
        if n.kind == "unsupported" or n.props.get("sql_override"):
            raise GenerationError(f"{self.g.job}: {n.name} ({n.tool_type}) is not SQL-expressible: "
                                  f"{n.props.get('reason') or 'SQL override'}")
        if n.kind == "target":
            raise GenerationError(f"{self.g.job}: target {n.name} used as an input")
        if self.is_active(n):
            cte = self._active(n, port)
            out = {c: ColExpr(f"src.{c}", cte) for c in self.columns[cte]}
        else:
            out = self._passive(n)
        self._exprs[key] = out
        return out

    def input_exprs(self, n: Node, edges: list[Edge] | None = None) -> dict[str, ColExpr]:
        result: dict[str, ColExpr] = {}
        for e in edges if edges is not None else self.g.inputs(n.id):
            up = self.exprs(e.src, e.src_port)
            pairs = e.fields if e.fields is not None else [(c, c) for c in up]
            for f, t in pairs:
                if f not in up:
                    raise GenerationError(f"{self.g.job}: {n.name} reads {f!r} which {e.src} does not produce")
                result[t] = up[f]
        bases = {c.base for c in result.values() if c.base is not None}
        if len(bases) > 1:
            raise GenerationError(f"{self.g.job}: {n.name} merges rows from different active sources {sorted(bases)}")
        return result

    def _passive(self, n: Node) -> dict[str, ColExpr]:
        if n.kind == "sequence":
            return {n.props.get("field", "nextval"): ColExpr(SEQ, None, (), int(n.props.get("start", 1)))}
        inputs = self.input_exprs(n)
        if n.kind in ("sort", "passthrough"):
            return dict(inputs)
        if n.kind == "project":
            out = dict(inputs) if n.props.get("passthrough_all") else {}
            for o in n.props.get("outputs", []):
                out[o.name] = self._output_expr(n, o, inputs)
            return out
        if n.kind == "lookup":
            ref_cte = self._lookup_ref(n)
            alias = f"lkp_{n.id}"
            conds, deps = [], set()
            for lk, ic in n.props["keys"]:
                if ic not in inputs:
                    raise GenerationError(f"{self.g.job}: lookup {n.name} key input {ic!r} not connected")
                conds.append(f"{alias}.{lk} = {inputs[ic].sql}")
                deps.update(inputs[ic].lookups)
            self.lookup_joins[n.id] = _LookupJoin(ref_cte, alias, " AND ".join(conds), tuple(sorted(deps)))
            base = next((c.base for c in inputs.values() if c.base), None)
            passthrough = n.props.get("passthrough")
            out = {c: inputs[c] for c in (passthrough if passthrough is not None else inputs) if c in inputs}
            for name, lcol in n.props["returns"]:
                out[name] = ColExpr(f"{alias}.{lcol}", base, tuple(sorted(deps | {n.id})))
            return out
        raise GenerationError(f"{self.g.job}: unsupported passive step {n.kind}")

    def _output_expr(self, n: Node, o, inputs: dict[str, ColExpr]) -> ColExpr:
        if o.is_passthrough:
            src = o.source or o.name
            if src not in inputs:
                raise GenerationError(f"{self.g.job}: {n.name}.{o.name} reads unconnected port {src!r}")
            return inputs[src]

        def resolve(c: str) -> str:
            if c not in inputs:
                raise KeyError(f"port {c!r} is not connected")
            if inputs[c].seq_start is not None:
                raise KeyError("sequence values used inside expressions")
            return inputs[c].sql

        sql, cols = self._translate(o.expr, resolve)
        base = next((inputs[c].base for c in cols if inputs[c].base), None)
        lookups = tuple(sorted({lk for c in cols for lk in inputs[c].lookups}))
        return ColExpr(sql, base, lookups)

    # ------------------------------------------------------------------ materialisation
    def _cte(self, name: str, sql: str, columns: list[str]) -> str:
        if name not in self.ctes:
            self.ctes[name] = sql
            self.columns[name] = columns
        return name

    def select(self, fields: dict[str, ColExpr], distinct: bool = False) -> str:
        bases = {c.base for c in fields.values() if c.base is not None}
        if len(bases) != 1:
            raise GenerationError(f"{self.g.job}: projection needs exactly one active source, got {sorted(bases)}")
        base = bases.pop()
        needed: set[str] = set()
        stack = [lk for c in fields.values() for lk in c.lookups]
        while stack:
            lk = stack.pop()
            if lk not in needed:
                needed.add(lk)
                stack.extend(self.lookup_joins[lk].deps)
        order_cols = ", ".join(f"src.{c}" for c in self.columns[base])
        items = []
        for name, ce in fields.items():
            sql = ce.sql
            if ce.seq_start is not None:
                offset = f" + {ce.seq_start - 1}" if ce.seq_start != 1 else ""
                sql = f"ROW_NUMBER() OVER (ORDER BY {order_cols}){offset}"
            items.append(sql if sql == f"src.{name}" else f"{sql} AS {name}")
        lines = [("SELECT DISTINCT" if distinct else "SELECT"), _indent(",\n".join(items)), f"FROM {base} AS src"]
        for lk in sorted(needed, key=lambda x: self._order[x]):
            j = self.lookup_joins[lk]
            lines.append(f"LEFT JOIN {j.ref_cte} AS {j.alias}\n    ON {j.condition}")
        return "\n".join(lines)

    def _lookup_ref(self, n: Node) -> str:
        keys = [lk for lk, _ in n.props["keys"]]
        cols = list(dict.fromkeys(keys + [lc for _, lc in n.props["returns"]]))
        rel = self.relation_for(n)
        sql = (f"SELECT\n{_indent(', '.join(cols))}\nFROM {rel}\n"
               f"QUALIFY ROW_NUMBER() OVER (PARTITION BY {', '.join(keys)} ORDER BY {', '.join(cols)}) = 1")
        return self._cte(f"n_{n.id}_ref", sql, cols)

    def _active(self, n: Node, port: str | None) -> str:
        name = f"n_{n.id}"
        if n.kind == "split":
            self._split(n)
            group = port or n.props.get("default_group")
            return f"{name}__{ident(group)}"
        if name in self.ctes:
            return name
        if n.kind == "source":
            cols = [c.name for c in n.props["columns"]]
            if not cols:
                raise GenerationError(f"{self.g.job}: source {n.name} has no columns")
            return self._cte(name, f"SELECT\n{_indent(', '.join(cols))}\nFROM {self.relation_for(n)}", cols)
        if n.kind == "union":
            return self._union(n)
        if n.kind == "join":
            return self._join(n)
        inputs = self.input_exprs(n)
        in_cte = self._cte(f"{name}_in", self.select(inputs), list(inputs))
        in_cols = list(inputs)
        ident_resolve: Callable[[str], str] = lambda c: c  # noqa: E731 - active steps read their own _in columns
        if n.kind == "filter":
            cond, _ = self._translate(n.props["condition"], ident_resolve)
            return self._cte(name, f"SELECT *\nFROM {in_cte}\nWHERE {cond}", in_cols)
        if n.kind == "sort":
            return self._cte(name, f"SELECT DISTINCT *\nFROM {in_cte}", in_cols)
        if n.kind == "project":
            outs, items = [], []
            if n.props.get("passthrough_all"):
                replaced = {o.name for o in n.props.get("outputs", [])}
                outs += [c for c in in_cols if c not in replaced]
                items += [c for c in in_cols if c not in replaced]
            for o in n.props.get("outputs", []):
                if o.is_passthrough:
                    items.append(o.source if o.source == o.name else f"{o.source} AS {o.name}")
                else:
                    sql, _ = self._translate(o.expr, ident_resolve)
                    items.append(f"{sql} AS {o.name}")
                outs.append(o.name)
            where = n.props.get("filter_sql")
            if n.props.get("filter"):
                where, _ = self._translate(n.props["filter"], ident_resolve)
            head = "SELECT DISTINCT" if n.props.get("distinct") else "SELECT"
            sql = f"{head}\n{_indent(_list(items))}\nFROM {in_cte}" + (f"\nWHERE {where}" if where else "")
            return self._cte(name, sql, outs)
        if n.kind == "aggregate":
            items, outs = [], []
            for o in n.props["outputs"]:
                if o.is_passthrough:
                    items.append(o.source if o.source == o.name else f"{o.source} AS {o.name}")
                elif o.expr_is_sql:
                    items.append(f"{o.expr} AS {o.name}")
                else:
                    sql, _ = self._translate(o.expr, ident_resolve)
                    items.append(f"{sql} AS {o.name}")
                outs.append(o.name)
            group = n.props.get("group_by") or []
            sql = f"SELECT\n{_indent(_list(items))}\nFROM {in_cte}"
            if group:
                sql += f"\nGROUP BY {', '.join(group)}"
            return self._cte(name, sql, outs)
        if n.kind == "lookup":  # inner lookup (SSIS no-match rows discarded)
            ref = self._lookup_ref(n)
            rets = [r for r, _ in n.props["returns"]]
            keep = [c for c in in_cols if c not in rets]
            items = [f"i.{c}" for c in keep] + [f"l.{lc} AS {r}" for r, lc in n.props["returns"]]
            on = " AND ".join(f"l.{lk} = i.{ic}" for lk, ic in n.props["keys"])
            sql = f"SELECT\n{_indent(_list(items))}\nFROM {in_cte} AS i\nINNER JOIN {ref} AS l\n    ON {on}"
            return self._cte(name, sql, keep + rets)
        raise GenerationError(f"{self.g.job}: unsupported active step {n.kind}")

    def _split(self, n: Node) -> None:
        base = f"n_{n.id}"
        if f"{base}_in" in self.ctes:
            return
        inputs = self.input_exprs(n)
        in_cte = self._cte(f"{base}_in", self.select(inputs), list(inputs))
        conds = []
        for gname, expr in n.props["groups"]:
            sql, _ = self._translate(expr, lambda c: c)
            conds.append((gname, f"COALESCE({sql}, FALSE)"))
        first = n.props.get("semantics") == "first_match"
        group_fields = n.props.get("group_fields") or {}
        for i, (gname, cond) in enumerate(conds):
            pred = cond
            if first and i:
                pred = " AND ".join([cond] + [f"NOT {c}" for _, c in conds[:i]])
            self._group_cte(f"{base}__{ident(gname)}", in_cte, list(inputs), group_fields.get(gname), pred)
        default = n.props.get("default_group")
        if default:
            pred = " AND ".join(f"NOT {c}" for _, c in conds) or "TRUE"
            self._group_cte(f"{base}__{ident(default)}", in_cte, list(inputs), group_fields.get(default), pred)

    def _group_cte(self, name: str, in_cte: str, in_cols: list[str], fields, pred: str) -> None:
        if fields:
            items = [c if c == o else f"{c} AS {o}" for c, o in fields]
            cols = [o for _, o in fields]
        else:
            items, cols = in_cols, in_cols
        self._cte(name, f"SELECT\n{_indent(', '.join(items))}\nFROM {in_cte}\nWHERE {pred}", cols)

    def _union(self, n: Node) -> str:
        edges = sorted(self.g.inputs(n.id), key=lambda e: (e.dst_port or "", e.src))
        branches = [self.input_exprs(n, [e]) for e in edges]
        cols = n.props.get("columns") or list(branches[0])
        parts = []
        for b in branches:
            base = next((v.base for v in b.values() if v.base), None)
            parts.append(self.select({c: b.get(c) or ColExpr("NULL", base) for c in cols}))
        return self._cte(f"n_{n.id}", "\nUNION ALL\n".join(parts), cols)

    def _join(self, n: Node) -> str:
        edges = self.g.inputs(n.id)
        master = [e for e in edges if e.dst_port == "master"]
        detail = [e for e in edges if e.dst_port != "master"]
        if not master or not detail:
            raise GenerationError(f"{self.g.job}: joiner {n.name} needs a master and a detail input")
        m_in, d_in = self.input_exprs(n, master), self.input_exprs(n, detail)
        m_cte = self._cte(f"n_{n.id}_m", self.select(m_in), list(m_in))
        d_cte = self._cte(f"n_{n.id}_d", self.select(d_in), list(d_in))
        outputs = n.props.get("outputs") or [(c, "detail") for c in d_in] + [(c, "master") for c in m_in]
        items = [f"{'m' if side == 'master' else 'd'}.{c}" for c, side in outputs]
        on = " AND ".join(f"m.{mf} = d.{df}" for mf, df in n.props["conditions"])
        jt = {"inner": "INNER JOIN", "left": "LEFT JOIN", "right": "RIGHT JOIN", "full": "FULL OUTER JOIN"}[n.props["join_type"]]
        sql = f"SELECT\n{_indent(', '.join(items))}\nFROM {d_cte} AS d\n{jt} {m_cte} AS m\n    ON {on}"
        return self._cte(f"n_{n.id}", sql, [c for c, _ in outputs])

    # ------------------------------------------------------------------ targets
    def build_target(self, target_id: str) -> TargetSQL:
        n = self.g.nodes[target_id]
        fields = self.input_exprs(n)
        order = [c.name for c in n.props.get("columns", [])]
        ordered = {c: fields[c] for c in order if c in fields}
        ordered.update({c: v for c, v in fields.items() if c not in ordered})
        final = self.select(ordered)
        body = ",\n".join(f"{name} AS (\n{_indent(sql)}\n)" for name, sql in self.ctes.items())
        sql = (f"WITH {body}\n\n{final}\n" if body else final + "\n")
        return TargetSQL(target_id, sql, list(ordered), list(self.ctes))


# --------------------------------------------------------------------------- lineage


@dataclass
class Lineage:
    kind: str                      # source|lookup|expr|aggregate|group|sequence|union|unknown
    table: str | None = None
    system: str | None = None
    column: str | None = None
    rows_dropped: bool = False     # a filter/split/inner join sits on the path
    fanout: bool = False           # a join/union sits on the path
    grouped_single: bool = False   # sole GROUP BY column of an aggregate
    literal_values: list[str] | None = None


def trace(g: MappingGraph, node_id: str, col: str, port: str | None = None, _depth: int = 0) -> Lineage:
    """Follow one output column back to where its values come from."""
    if _depth > len(g.nodes) + 2:
        return Lineage("unknown")
    n = g.nodes[node_id]

    def up(name: str, edges: list[Edge] | None = None) -> Lineage:
        for e in edges if edges is not None else g.inputs(node_id):
            pairs = e.fields if e.fields is not None else None
            if pairs is None:
                return trace(g, e.src, name, e.src_port, _depth + 1)
            for f, t in pairs:
                if t == name:
                    return trace(g, e.src, f, e.src_port, _depth + 1)
        return Lineage("unknown")

    def mark(lin: Lineage, **flags) -> Lineage:
        for k, v in flags.items():
            setattr(lin, k, getattr(lin, k) or v)
        return lin

    if n.kind == "source":
        return Lineage("source", n.props.get("table"), n.props.get("system"), col)
    if n.kind == "sequence":
        return Lineage("sequence")
    if n.kind == "target":
        return up(col)
    if n.kind in ("filter", "sort"):
        return mark(up(col), rows_dropped=n.kind == "filter")
    if n.kind == "split":
        src = col
        for gname, fields in (n.props.get("group_fields") or {}).items():
            if gname == port:
                src = next((i for i, o in fields if o == col), col)
        return mark(up(src), rows_dropped=True)
    if n.kind == "project":
        for o in n.props.get("outputs", []):
            if o.name == col:
                if o.is_passthrough:
                    return mark(up(o.source or col), rows_dropped=bool(n.props.get("filter_sql") or n.props.get("filter")))
                return Lineage("expr", literal_values=o.literal_values)
        if n.props.get("passthrough_all"):
            return up(col)
        return Lineage("unknown")
    if n.kind == "lookup":
        for out, lcol in n.props.get("returns", []):
            if out == col:
                return Lineage("lookup", n.props.get("table"), n.props.get("system"), lcol)
        return mark(up(col), rows_dropped=n.props.get("join") == "inner")
    if n.kind == "aggregate":
        group = n.props.get("group_by") or []
        for o in n.props.get("outputs", []):
            if o.name == col:
                if o.is_passthrough and (o.source or col) in group:
                    lin = up(o.source or col)
                    lin.grouped_single = len(group) == 1
                    lin.fanout = False
                    return lin
                return Lineage("aggregate")
        return Lineage("unknown")
    if n.kind == "join":
        side = next((s for c, s in n.props.get("outputs", []) if c == col), None)
        edges = [e for e in g.inputs(node_id) if (e.dst_port == "master") == (side == "master")]
        return mark(up(col, edges), fanout=side == "master", rows_dropped=n.props.get("join_type") != "left")
    if n.kind == "union":
        branches = [up(col, [e]) for e in g.inputs(node_id)]
        if branches and all(b.kind == "source" for b in branches):
            return mark(branches[0], fanout=True)
        return Lineage("union", fanout=True)
    return Lineage("unknown")
