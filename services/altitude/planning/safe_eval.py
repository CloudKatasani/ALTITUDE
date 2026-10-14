"""Safe evaluator for rule conditions stored as data (no ``eval``/``exec``).

Grammar (case-insensitive keywords)::

    expr    := or
    or      := and ("or" and)*
    and     := not ("and" not)*
    not     := "not" not | cmp
    cmp     := sum [("<" | "<=" | ">" | ">=" | "==" | "!=" | "in" | "not in") sum]
    sum     := term (("+" | "-") term)*
    term    := unary (("*" | "/") unary)*
    unary   := "-" unary | atom
    atom    := NUMBER | STRING | true | false | null | NAME | "(" expr ")" | "[" [expr ("," expr)*] "]"

``NAME`` is a dotted identifier looked up in the supplied variables
(``a.b`` walks nested mappings); names starting with ``rubric.`` resolve
through a :class:`~altitude.core.rubric.RubricSet`. A name with no value
raises :class:`MissingInput` so callers can treat the rule as not evaluable
(and count it against data completeness) instead of guessing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Mapping

from altitude.core.errors import AltitudeError
from altitude.core.rubric import RubricSet, is_ref


class ExpressionError(AltitudeError):
    """The expression is malformed or applies an operator to incompatible values."""


class MissingInput(AltitudeError):
    """The expression references a variable with no value."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"missing input {name!r}")


_TOKEN = re.compile(r"""
    \s*(?:
      (?P<num>\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)
    | (?P<str>'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")
    | (?P<op><=|>=|==|!=|<|>|\+|-|\*|/|\(|\)|\[|\]|,)
    | (?P<name>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
    )""", re.VERBOSE)
_KEYWORDS = {"and", "or", "not", "in", "true", "false", "null"}
_EXPR_SIZE_GUARD = 2000


@dataclass(frozen=True)
class Tok:
    kind: str
    value: Any


def _tokenize(src: str) -> list[Tok]:
    if len(src) > _EXPR_SIZE_GUARD:
        raise ExpressionError("expression too long")
    out, pos = [], 0
    while pos < len(src):
        if src[pos:].strip() == "":
            break
        m = _TOKEN.match(src, pos)
        if not m or m.end() == pos:
            raise ExpressionError(f"unexpected character at {pos}: {src[pos:pos + 10]!r}")
        pos = m.end()
        if m.group("num") is not None:
            text = m.group("num")
            out.append(Tok("num", float(text) if any(c in text for c in ".eE") else int(text)))
        elif m.group("str") is not None:
            raw = m.group("str")[1:-1]
            out.append(Tok("str", re.sub(r"\\(.)", r"\1", raw)))
        elif m.group("op") is not None:
            out.append(Tok("op", m.group("op")))
        else:
            name = m.group("name")
            low = name.lower()
            out.append(Tok("kw", low) if low in _KEYWORDS else Tok("name", name))
    out.append(Tok("end", None))
    return out


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.t = toks
        self.i = 0

    def peek(self) -> Tok:
        return self.t[self.i]

    def take(self) -> Tok:
        tok = self.t[self.i]
        self.i += 1
        return tok

    def accept(self, kind: str, value: Any = None) -> bool:
        tok = self.peek()
        if tok.kind == kind and (value is None or tok.value == value):
            self.i += 1
            return True
        return False

    def expect(self, kind: str, value: Any = None) -> Tok:
        tok = self.take()
        if tok.kind != kind or (value is not None and tok.value != value):
            raise ExpressionError(f"expected {value or kind}, got {tok.value!r}")
        return tok

    def parse(self) -> tuple:
        node = self.or_()
        if self.peek().kind != "end":
            raise ExpressionError(f"unexpected token {self.peek().value!r}")
        return node

    def or_(self) -> tuple:
        node = self.and_()
        while self.accept("kw", "or"):
            node = ("or", node, self.and_())
        return node

    def and_(self) -> tuple:
        node = self.not_()
        while self.accept("kw", "and"):
            node = ("and", node, self.not_())
        return node

    def not_(self) -> tuple:
        if self.peek() == Tok("kw", "not") and not (self.t[self.i + 1] == Tok("kw", "in")):
            self.take()
            return ("not", self.not_())
        return self.cmp()

    def cmp(self) -> tuple:
        left = self.sum()
        tok = self.peek()
        if tok.kind == "op" and tok.value in {"<", "<=", ">", ">=", "==", "!="}:
            self.take()
            return ("cmp", tok.value, left, self.sum())
        if tok == Tok("kw", "in"):
            self.take()
            return ("cmp", "in", left, self.sum())
        if tok == Tok("kw", "not") and self.t[self.i + 1] == Tok("kw", "in"):
            self.i += 2
            return ("cmp", "not in", left, self.sum())
        return left

    def sum(self) -> tuple:
        node = self.term()
        while self.peek().kind == "op" and self.peek().value in {"+", "-"}:
            node = ("arith", self.take().value, node, self.term())
        return node

    def term(self) -> tuple:
        node = self.unary()
        while self.peek().kind == "op" and self.peek().value in {"*", "/"}:
            node = ("arith", self.take().value, node, self.unary())
        return node

    def unary(self) -> tuple:
        if self.accept("op", "-"):
            return ("neg", self.unary())
        return self.atom()

    def atom(self) -> tuple:
        tok = self.take()
        if tok.kind in {"num", "str"}:
            return ("lit", tok.value)
        if tok.kind == "kw" and tok.value in {"true", "false", "null"}:
            return ("lit", {"true": True, "false": False, "null": None}[tok.value])
        if tok.kind == "name":
            return ("var", tok.value)
        if tok == Tok("op", "("):
            node = self.or_()
            self.expect("op", ")")
            return node
        if tok == Tok("op", "["):
            items = []
            if not self.accept("op", "]"):
                items.append(self.or_())
                while self.accept("op", ","):
                    items.append(self.or_())
                self.expect("op", "]")
            return ("list", tuple(items))
        raise ExpressionError(f"unexpected token {tok.value!r}")


@lru_cache(maxsize=512)
def compile_expr(src: str) -> tuple:
    """Parse once; the AST is a tree of plain tuples."""
    if not isinstance(src, str) or not src.strip():
        raise ExpressionError("empty expression")
    return _Parser(_tokenize(src)).parse()


def variables(src: str) -> set[str]:
    """Names (excluding rubric references) an expression reads."""
    out: set[str] = set()

    def walk(n: Any) -> None:
        if isinstance(n, tuple):
            if n and n[0] == "var" and not is_ref(n[1]):
                out.add(n[1])
            for c in n[1:]:
                walk(c)

    walk(compile_expr(src))
    return out


def _lookup(name: str, env: Mapping[str, Any], rubrics: RubricSet | None) -> Any:
    if is_ref(name):
        if rubrics is None:
            raise ExpressionError(f"rubric reference {name!r} needs a RubricSet")
        return rubrics.get(name)
    if name in env:
        value = env[name]
    else:
        node: Any = env
        for part in name.split("."):
            if isinstance(node, Mapping) and part in node:
                node = node[part]
            else:
                raise MissingInput(name)
        value = node
    if value is None:
        raise MissingInput(name)
    return value


def _num(v: Any, op: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ExpressionError(f"operator {op!r} needs numbers, got {v!r}")
    return v


def _eval(n: tuple, env: Mapping[str, Any], rubrics: RubricSet | None) -> Any:
    kind = n[0]
    if kind == "lit":
        return n[1]
    if kind == "var":
        return _lookup(n[1], env, rubrics)
    if kind == "list":
        return [_eval(c, env, rubrics) for c in n[1]]
    if kind == "neg":
        return -_num(_eval(n[1], env, rubrics), "-")
    if kind == "not":
        return not _truth(_eval(n[1], env, rubrics))
    if kind in {"and", "or"}:
        # Kleene logic: a missing input only matters when the other operand cannot decide the result.
        decisive = kind == "or"
        try:
            left = _truth(_eval(n[1], env, rubrics))
        except MissingInput:
            if _truth(_eval(n[2], env, rubrics)) == decisive:
                return decisive
            raise
        if left == decisive:
            return decisive
        return _truth(_eval(n[2], env, rubrics))
    if kind == "arith":
        a, b = _num(_eval(n[2], env, rubrics), n[1]), _num(_eval(n[3], env, rubrics), n[1])
        if n[1] == "+":
            return a + b
        if n[1] == "-":
            return a - b
        if n[1] == "*":
            return a * b
        if b == 0:
            raise ExpressionError("division by zero")
        return a / b
    if kind == "cmp":
        op, a, b = n[1], _eval(n[2], env, rubrics), _eval(n[3], env, rubrics)
        if op in {"in", "not in"}:
            if not isinstance(b, (list, str)):
                raise ExpressionError(f"'{op}' needs a list or string on the right")
            return (a in b) if op == "in" else (a not in b)
        if op == "==":
            return a == b
        if op == "!=":
            return a != b
        if not (isinstance(a, str) and isinstance(b, str)):
            a, b = _num(a, op), _num(b, op)
        return {"<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    raise ExpressionError(f"unknown node {kind!r}")


def _truth(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    raise ExpressionError(f"expected a boolean, got {v!r}")


def evaluate(src: str, env: Mapping[str, Any] | None = None, rubrics: RubricSet | None = None) -> Any:
    return _eval(compile_expr(src), env or {}, rubrics)


def evaluate_bool(src: str, env: Mapping[str, Any] | None = None, rubrics: RubricSet | None = None) -> bool:
    return _truth(evaluate(src, env, rubrics))
