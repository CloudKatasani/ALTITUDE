"""Expression translators: SSIS expression language and Informatica transformation language -> Snowflake SQL.

Both are tokenised and parsed (precedence climbing) into a small AST, then emitted as SQL that is valid
Snowflake (and transpiles to DuckDB for the dbt harness). Function names map through the knowledge files
(``knowledge/etl/components_*.yaml``); anything unknown raises :class:`UnsupportedExpression`, which makes
the job "complex" with an ``ETL-GEN-03`` issue instead of emitting wrong SQL.

Variables / parameters (``@[User::LoadDate]``, ``$$RUN_DATE``) become dbt vars: ``{{ var('load_date') }}``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from . import kb
from .naming import ident


class UnsupportedExpression(ValueError):
    """The expression uses a construct with no safe SQL translation."""


@dataclass
class Tok:
    kind: str     # num|str|ident|op|cast|param|lkp|eof
    value: Any
    pos: int


@dataclass
class Translation:
    sql: str
    columns: set[str] = field(default_factory=set)      # identifiers referenced (normalised)
    variables: set[str] = field(default_factory=set)    # dbt vars referenced
    literal_values: list[str] | None = None             # when every branch is a string literal (accepted_values)
    is_aggregate: bool = False
    ast: Any = None
    comparisons: list[tuple[str, str]] = field(default_factory=list)  # (column, string literal) compared


# --------------------------------------------------------------------------- tokenisers


_NUM = re.compile(r"\d+(?:\.\d+)?(?:[eE][+-]?\d+)?[LlUu]?")
_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_$#]*")


def _tokens_ssis(text: str) -> list[Tok]:
    out: list[Tok] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c == '"':
            j, buf = i + 1, []
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    buf.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(text[j + 1], text[j + 1]))
                    j += 2
                    continue
                buf.append(text[j])
                j += 1
            out.append(Tok("str", "".join(buf), i))
            i = j + 1
            continue
        if text.startswith("@[", i):
            j = text.index("]", i)
            out.append(Tok("param", text[i + 2:j].split("::")[-1], i))
            i = j + 1
            continue
        if c == "[":
            j = text.index("]", i)
            out.append(Tok("ident", text[i + 1:j], i))
            i = j + 1
            continue
        m = re.compile(r"\(\s*(DT_\w+)\s*((?:,\s*\d+\s*)*)\)").match(text, i)
        if m:
            params = [p.strip() for p in m.group(2).split(",") if p.strip()]
            out.append(Tok("cast", (m.group(1).upper(), params), i))
            i = m.end()
            continue
        m = _NUM.match(text, i)
        if m:
            out.append(Tok("num", m.group(0).rstrip("LlUu"), i))
            i = m.end()
            continue
        m = _ID.match(text, i)
        if m:
            out.append(Tok("ident", m.group(0), i))
            i = m.end()
            continue
        for op in ("==", "!=", ">=", "<=", "&&", "||", ">", "<", "+", "-", "*", "/", "%", "!", "?", ":", "(", ")", ","):
            if text.startswith(op, i):
                out.append(Tok("op", op, i))
                i += len(op)
                break
        else:
            raise UnsupportedExpression(f"unexpected character {c!r} at {i}")
    out.append(Tok("eof", None, n))
    return out


def _tokens_informatica(text: str) -> list[Tok]:
    out: list[Tok] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if text.startswith("--", i) or text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
            continue
        if c == "'":
            j, buf = i + 1, []
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    buf.append("'")
                    j += 2
                    continue
                if text[j] == "'":
                    break
                buf.append(text[j])
                j += 1
            out.append(Tok("str", "".join(buf), i))
            i = j + 1
            continue
        if text.startswith(":LKP.", i) or text.startswith(":SP.", i) or text.startswith(":MCR.", i):
            m = _ID.match(text, i + text[i + 1:].index(".") + 2)
            out.append(Tok("lkp", m.group(0) if m else "", i))
            i = m.end() if m else n
            continue
        if text.startswith("$$", i) or (c == "$" and text.startswith("$PM", i)):
            m = re.compile(r"\$\$?[A-Za-z_][A-Za-z0-9_]*").match(text, i)
            out.append(Tok("param", m.group(0).lstrip("$"), i))
            i = m.end()
            continue
        m = _NUM.match(text, i)
        if m:
            out.append(Tok("num", m.group(0).rstrip("LlUu"), i))
            i = m.end()
            continue
        m = _ID.match(text, i)
        if m:
            out.append(Tok("ident", m.group(0), i))
            i = m.end()
            continue
        for op in ("||", "<>", "!=", "^=", ">=", "<=", "=", ">", "<", "+", "-", "*", "/", "%", "(", ")", ","):
            if text.startswith(op, i):
                out.append(Tok("op", "<>" if op in ("!=", "^=") else op, i))
                i += len(op)
                break
        else:
            raise UnsupportedExpression(f"unexpected character {c!r} at {i}")
    out.append(Tok("eof", None, n))
    return out


# --------------------------------------------------------------------------- AST + parser

# AST nodes are tuples: ("lit", sql) ("col", name) ("var", name) ("func", NAME, [args]) ("bin", op, l, r)
# ("not", e) ("neg", e) ("case", [(cond, val)], else) ("cast", type, e) ("isnull", e)


class _Parser:
    def __init__(self, toks: list[Tok], dialect: str):
        self.toks = toks
        self.i = 0
        self.dialect = dialect

    def peek(self) -> Tok:
        return self.toks[self.i]

    def take(self) -> Tok:
        t = self.toks[self.i]
        self.i += 1
        return t

    def accept(self, kind: str, value: Any = None) -> Tok | None:
        t = self.peek()
        if t.kind == kind and (value is None or (isinstance(t.value, str) and t.value.upper() == str(value).upper())):
            return self.take()
        return None

    def expect(self, kind: str, value: Any = None) -> Tok:
        t = self.accept(kind, value)
        if t is None:
            raise UnsupportedExpression(f"expected {value or kind} at {self.peek().pos}, found {self.peek().value!r}")
        return t

    # -- SSIS: ternary > || > && > == != > relational > + - > * / % > unary
    def parse(self) -> tuple:
        node = self.ssis_ternary() if self.dialect == "ssis" else self.inf_or()
        if self.peek().kind != "eof":
            raise UnsupportedExpression(f"unexpected token {self.peek().value!r} at {self.peek().pos}")
        return node

    def ssis_ternary(self) -> tuple:
        cond = self.ssis_binary(0)
        if self.accept("op", "?"):
            a = self.ssis_ternary()
            self.expect("op", ":")
            b = self.ssis_ternary()
            return ("case", [(cond, a)], b)
        return cond

    _SSIS_LEVELS = [("||",), ("&&",), ("==", "!="), (">", "<", ">=", "<="), ("+", "-"), ("*", "/", "%")]
    _SSIS_MAP = {"||": "OR", "&&": "AND", "==": "=", "!=": "<>"}

    def ssis_binary(self, level: int) -> tuple:
        if level == len(self._SSIS_LEVELS):
            return self.ssis_unary()
        left = self.ssis_binary(level + 1)
        while self.peek().kind == "op" and self.peek().value in self._SSIS_LEVELS[level]:
            op = self.take().value
            right = self.ssis_binary(level + 1)
            sql_op = self._SSIS_MAP.get(op, op)
            if op == "+" and (_is_string(left) or _is_string(right)):
                sql_op = "||"
            left = ("bin", sql_op, left, right)
        return left

    def ssis_unary(self) -> tuple:
        if self.accept("op", "!"):
            return ("not", self.ssis_unary())
        if self.accept("op", "-"):
            return ("neg", self.ssis_unary())
        t = self.peek()
        if t.kind == "cast":
            self.take()
            return ("cast", t.value, self.ssis_unary())
        return self.primary()

    # -- Informatica: OR > AND > NOT > comparison > || > + - > * / % > unary
    def inf_or(self) -> tuple:
        left = self.inf_and()
        while self.accept("ident", "OR"):
            left = ("bin", "OR", left, self.inf_and())
        return left

    def inf_and(self) -> tuple:
        left = self.inf_not()
        while self.accept("ident", "AND"):
            left = ("bin", "AND", left, self.inf_not())
        return left

    def inf_not(self) -> tuple:
        if self.accept("ident", "NOT"):
            return ("not", self.inf_not())
        return self.inf_cmp()

    def inf_cmp(self) -> tuple:
        left = self.inf_concat()
        while self.peek().kind == "op" and self.peek().value in ("=", "<>", ">", "<", ">=", "<="):
            op = self.take().value
            left = ("bin", op, left, self.inf_concat())
        return left

    def inf_concat(self) -> tuple:
        left = self.inf_add()
        while self.accept("op", "||"):
            left = ("bin", "||", left, self.inf_add())
        return left

    def inf_add(self) -> tuple:
        left = self.inf_mul()
        while self.peek().kind == "op" and self.peek().value in ("+", "-"):
            op = self.take().value
            left = ("bin", op, left, self.inf_mul())
        return left

    def inf_mul(self) -> tuple:
        left = self.inf_unary()
        while self.peek().kind == "op" and self.peek().value in ("*", "/", "%"):
            op = self.take().value
            left = ("bin", op, left, self.inf_unary())
        return left

    def inf_unary(self) -> tuple:
        if self.accept("op", "-"):
            return ("neg", self.inf_unary())
        if self.accept("op", "+"):
            return self.inf_unary()
        return self.primary()

    # -- shared
    def primary(self) -> tuple:
        t = self.take()
        if t.kind == "num":
            return ("lit", t.value)
        if t.kind == "str":
            return ("str", t.value)
        if t.kind == "param":
            return ("var", t.value)
        if t.kind == "lkp":
            raise UnsupportedExpression(f"unconnected lookup / procedure call :{t.value} is row-by-row logic")
        if t.kind == "op" and t.value == "(":
            inner = self.ssis_ternary() if self.dialect == "ssis" else self.inf_or()
            self.expect("op", ")")
            return inner
        if t.kind == "ident":
            name = t.value
            up = name.upper()
            if self.accept("op", "("):
                args = []
                if not self.accept("op", ")"):
                    while True:
                        args.append(self.ssis_ternary() if self.dialect == "ssis" else self.inf_or())
                        if self.accept("op", ")"):
                            break
                        self.expect("op", ",")
                return ("func", up, args)
            if up in ("TRUE", "FALSE"):
                return ("lit", up)
            if up == "NULL":
                return ("lit", "NULL")
            return ("col", name)
        raise UnsupportedExpression(f"unexpected token {t.value!r} at {t.pos}")


def _is_string(node: tuple) -> bool:
    return node[0] == "str" or (node[0] == "func" and node[1] in {"UPPER", "LOWER", "TRIM", "LTRIM", "RTRIM",
                                                                   "SUBSTRING", "REPLACE", "LEFT", "RIGHT"}) \
        or (node[0] == "cast" and node[1][0] in {"DT_WSTR", "DT_STR", "DT_TEXT", "DT_NTEXT"}) \
        or (node[0] == "bin" and node[1] == "||")


# --------------------------------------------------------------------------- emitter


_ASSOC = {"AND", "OR", "+", "*", "||"}
_AGGREGATES = {"SUM", "COUNT", "AVG", "MIN", "MAX", "MEDIAN"}


class _Emitter:
    def __init__(self, tool: str, resolve: Callable[[str], str] | None = None,
                 var_types: dict[str, str] | None = None):
        self.tool = tool
        self.resolve = resolve
        self.var_types = var_types or {}
        comp = kb.components(tool)
        self.functions = comp["functions"]
        self.casts = comp.get("casts", {})
        self.parts = {k.lower(): v for k, v in comp.get("date_parts", {}).items()}
        self.keyword_values = {k.upper() for k in comp.get("keyword_values", [])}
        self.columns: set[str] = set()
        self.variables: set[str] = set()
        self.aggregate = False

    def emit(self, node: tuple, parent_op: str | None = None) -> str:
        kind = node[0]
        if kind == "lit":
            return node[1]
        if kind == "str":
            return "'" + node[1].replace("'", "''") + "'"
        if kind == "var":
            name = ident(node[1])
            self.variables.add(name)
            ref = '{{ var("' + name + '") }}'
            vtype = self.var_types.get(name, "string")
            if vtype == "number":
                return ref
            if vtype in ("timestamp", "date", "boolean"):
                return f"CAST('{ref}' AS {vtype.upper()})"
            return f"'{ref}'"
        if kind == "col":
            if node[1].upper() in self.keyword_values:
                return self._func(node[1].upper(), [])
            name = ident(node[1])
            self.columns.add(name)
            if self.resolve is not None:
                sql = self.resolve(name)
                return sql if re.fullmatch(r'[\w."]+', sql) else f"({sql})"
            return name
        if kind == "not":
            return f"NOT ({self.emit(node[1])})"
        if kind == "neg":
            return f"-({self.emit(node[1])})"
        if kind == "cast":
            dt, params = node[1]
            tmpl = self.casts.get(dt)
            if tmpl is None:
                raise UnsupportedExpression(f"cast to {dt} has no mapping")
            target = re.sub(r"\(\{\d\}(,\{\d\})?\)", "", tmpl) if not params else tmpl.format(*params)
            return f"CAST({self.emit(node[2])} AS {target})"
        if kind == "case":
            whens = " ".join(f"WHEN {self.emit(c)} THEN {self.emit(v)}" for c, v in node[1])
            other = f" ELSE {self.emit(node[2])}" if node[2] is not None else ""
            return f"CASE {whens}{other} END"
        if kind == "bin":
            op = node[1]
            left = self.emit(node[2], op)
            right = self.emit(node[3], op)
            sql = f"{left} {op} {right}"
            if parent_op is not None and not (parent_op == op and op in _ASSOC):
                return f"({sql})"
            return sql
        if kind == "func":
            return self._func(node[1], node[2])
        raise UnsupportedExpression(f"unknown node {kind}")

    def _func(self, name: str, args: list) -> str:
        spec = self.functions.get(name)
        if spec is None:
            raise UnsupportedExpression(f"function {name} has no SQL mapping")
        if name in _AGGREGATES:
            self.aggregate = True
        if isinstance(spec, dict):
            return getattr(self, f"_special_{spec['special']}")(args)
        placeholders = {int(x) for x in re.findall(r"\{(\d+)\}", spec)}
        if placeholders and max(placeholders) >= len(args):
            raise UnsupportedExpression(f"{name} expects {max(placeholders) + 1} argument(s), got {len(args)}")
        if len(args) > len(placeholders):
            raise UnsupportedExpression(f"{name} with {len(args)} arguments is not mapped")
        return spec.format(*[self.emit(a) for a in args])

    def _part(self, node: tuple) -> str:
        if node[0] != "str":
            raise UnsupportedExpression("date part must be a string literal")
        part = self.parts.get(node[1].lower())
        if part is None:
            raise UnsupportedExpression(f"date part {node[1]!r} not mapped")
        return part

    # -- specials
    def _special_iif(self, args: list) -> str:
        if len(args) not in (2, 3):
            raise UnsupportedExpression("IIF expects 2 or 3 arguments")
        return self.emit(("case", [(args[0], args[1])], args[2] if len(args) == 3 else ("lit", "NULL")))

    def _special_decode(self, args: list) -> str:
        if len(args) < 3:  # threshold-ok: DECODE arity
            raise UnsupportedExpression("DECODE expects at least 3 arguments")
        subject, rest = args[0], args[1:]
        default = rest.pop() if len(rest) % 2 else None
        pairs = list(zip(rest[0::2], rest[1::2]))
        if subject == ("lit", "TRUE"):
            return self.emit(("case", pairs, default))
        return self.emit(("case", [(("bin", "=", subject, s), r) for s, r in pairs], default))

    def _special_substr(self, args: list) -> str:
        if len(args) == 2:
            return f"SUBSTR({self.emit(args[0])}, {self.emit(args[1])})"
        if len(args) == 3:
            return f"SUBSTR({self.emit(args[0])}, {self.emit(args[1])}, {self.emit(args[2])})"
        raise UnsupportedExpression("SUBSTR expects 2 or 3 arguments")

    def _special_replacestr(self, args: list) -> str:
        if len(args) != 4 or args[0] not in (("lit", "1"), ("lit", "TRUE")):
            raise UnsupportedExpression("REPLACESTR is only mapped for case-sensitive single replacement")
        return f"REPLACE({self.emit(args[1])}, {self.emit(args[2])}, {self.emit(args[3])})"

    def _special_to_char(self, args: list) -> str:
        if len(args) == 1:
            return f"CAST({self.emit(args[0])} AS VARCHAR)"
        if len(args) == 2:
            return f"TO_CHAR({self.emit(args[0])}, {self.emit(args[1])})"
        raise UnsupportedExpression("TO_CHAR expects 1 or 2 arguments")

    def _special_to_decimal(self, args: list) -> str:
        scale = args[1][1] if len(args) == 2 and args[1][0] == "lit" else "0" if len(args) == 1 else None
        if scale is None:
            raise UnsupportedExpression("TO_DECIMAL scale must be a literal")
        return f"CAST({self.emit(args[0])} AS DECIMAL(38, {scale}))"

    def _special_add_to_date(self, args: list) -> str:
        if len(args) != 3:
            raise UnsupportedExpression("ADD_TO_DATE expects 3 arguments")
        return f"DATEADD({self._part(args[1])}, {self.emit(args[2])}, {self.emit(args[0])})"

    def _special_date_diff(self, args: list) -> str:
        if len(args) != 3:
            raise UnsupportedExpression("DATE_DIFF expects 3 arguments")
        return f"DATEDIFF({self._part(args[2])}, {self.emit(args[1])}, {self.emit(args[0])})"

    def _special_get_date_part(self, args: list) -> str:
        if len(args) != 2:
            raise UnsupportedExpression("GET_DATE_PART expects 2 arguments")
        return f"DATE_PART({self._part(args[1])}, {self.emit(args[0])})"

    def _special_dateadd(self, args: list) -> str:
        if len(args) != 3:
            raise UnsupportedExpression("DATEADD expects 3 arguments")
        return f"DATEADD({self._part(args[0])}, {self.emit(args[1])}, {self.emit(args[2])})"

    def _special_datediff(self, args: list) -> str:
        if len(args) != 3:
            raise UnsupportedExpression("DATEDIFF expects 3 arguments")
        return f"DATEDIFF({self._part(args[0])}, {self.emit(args[1])}, {self.emit(args[2])})"

    def _special_datepart(self, args: list) -> str:
        if len(args) != 2:
            raise UnsupportedExpression("DATEPART expects 2 arguments")
        return f"DATE_PART({self._part(args[0])}, {self.emit(args[1])})"

    def _special_typed_null(self, args: list) -> str:
        return "NULL"


def _literal_values(node: tuple) -> list[str] | None:
    """All result branches are string literals -> the set of values (for accepted_values tests)."""
    if node[0] == "str":
        return [node[1]]
    if node[0] == "case":
        vals: list[str] = []
        branches = [v for _, v in node[1]] + ([node[2]] if node[2] is not None else [])
        for b in branches:
            sub = _literal_values(b)
            if sub is None:
                return None
            vals += [v for v in sub if v not in vals]
        return vals
    if node[0] == "func" and node[1] in {"IIF", "DECODE"}:
        args = node[2]
        if node[1] == "IIF":
            branches = args[1:]
        else:
            rest = args[1:]
            branches = rest[1::2] + ([rest[-1]] if len(rest) % 2 else [])
        vals = []
        for b in branches:
            sub = _literal_values(b)
            if sub is None:
                return None
            vals += [v for v in sub if v not in vals]
        return vals
    return None


def _comparisons(node: Any) -> list[tuple[str, str]]:
    """(column, literal) pairs compared for equality anywhere in the expression (synthetic-data domains)."""
    out: list[tuple[str, str]] = []
    if isinstance(node, list):
        for item in node:
            out += _comparisons(item)
        return out
    if not isinstance(node, tuple) or not node:
        return out
    if not isinstance(node[0], str):  # (cond, value) pair inside a CASE
        for item in node:
            out += _comparisons(item)
        return out
    if node[0] == "bin" and node[1] in ("=", "<>"):
        a, b = node[2], node[3]
        if a[0] == "col" and b[0] == "str":
            out.append((ident(a[1]), b[1]))
        elif b[0] == "col" and a[0] == "str":
            out.append((ident(b[1]), a[1]))
    if node[0] == "func" and node[1] == "DECODE" and node[2] and node[2][0][0] == "col":
        subject = ident(node[2][0][1])
        rest = node[2][1:]
        searches = rest[0::2][: len(rest) // 2]
        out += [(subject, v[1]) for v in searches if v[0] == "str"]
    for child in node[1:]:
        if isinstance(child, (tuple, list)):
            out += _comparisons(child)
    return out


def translate(text: str, tool: str, resolve: Callable[[str], str] | None = None,
              var_types: dict[str, str] | None = None) -> Translation:
    """Translate one tool expression into Snowflake SQL.

    ``resolve`` maps a (normalised) column name to the SQL it stands for - used to collapse chains of
    passive transformations into one expression over their active source. ``var_types`` maps dbt var
    names to number|string|timestamp|date|boolean so variables are emitted with the right SQL type.
    """
    if text is None or not str(text).strip():
        raise UnsupportedExpression("empty expression")
    dialect = "ssis" if tool == "ssis" else "informatica"
    toks = _tokens_ssis(text) if dialect == "ssis" else _tokens_informatica(text)
    ast = _Parser(toks, dialect).parse()
    em = _Emitter(tool, resolve, var_types)
    sql = em.emit(ast)
    return Translation(sql=sql, columns=em.columns, variables=em.variables, literal_values=_literal_values(ast),
                       is_aggregate=em.aggregate, ast=ast, comparisons=sorted(set(_comparisons(ast))))
