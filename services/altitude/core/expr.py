"""Safe evaluation of rule conditions stored as data.

Knowledge files express conditions such as
``"deadline_weeks < 26 and procedural_code_share > 0.4"``. They are evaluated
here with a whitelist AST interpreter — never ``eval``. Names resolve against a
context mapping; ``rubric.*`` dotted references resolve through a ``RubricSet``.
Unknown names raise ``ExpressionError`` so a typo cannot silently evaluate to
false.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

from .errors import AltitudeError
from .rubric import RubricSet

_BIN = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
}
_CMP = {
    ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
    ast.Eq: operator.eq, ast.NotEq: operator.ne,
    ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_, ast.IsNot: operator.is_not,
}
_FUNCS = {"min": min, "max": max, "abs": abs, "len": len, "round": round}


class ExpressionError(AltitudeError):
    pass


def _dotted(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def evaluate(expression: str, context: Mapping[str, Any], rubrics: RubricSet | None = None) -> Any:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise ExpressionError(f"invalid expression {expression!r}: {e.msg}") from None

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return [ev(e) for e in node.elts]
        if isinstance(node, ast.Name):
            if node.id in ("true", "True"):
                return True
            if node.id in ("false", "False"):
                return False
            if node.id in ("null", "None"):
                return None
            if node.id not in context:
                raise ExpressionError(f"unknown name {node.id!r} in {expression!r}")
            return context[node.id]
        if isinstance(node, ast.Attribute):
            dotted = _dotted(node)
            if dotted and dotted.startswith("rubric."):
                if rubrics is None:
                    raise ExpressionError(f"rubric reference {dotted!r} needs a RubricSet")
                return rubrics.get(dotted)
            if dotted and dotted in context:
                return context[dotted]
            base = ev(node.value)
            if isinstance(base, Mapping) and node.attr in base:
                return base[node.attr]
            raise ExpressionError(f"unknown attribute {dotted or node.attr!r} in {expression!r}")
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for v in node.values:
                    result = ev(v)
                    if not result:
                        return result
                return result
            result = False
            for v in node.values:
                result = ev(v)
                if result:
                    return result
            return result
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return not ev(node.operand)
            if isinstance(node.op, ast.USub):
                return -ev(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +ev(node.operand)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
            return _BIN[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.Compare):
            left = ev(node.left)
            for op, comp in zip(node.ops, node.comparators):
                right = ev(comp)
                if type(op) not in _CMP:
                    raise ExpressionError(f"operator {type(op).__name__} not allowed")
                if left is None or right is None:
                    if type(op) not in (ast.Eq, ast.NotEq, ast.Is, ast.IsNot):
                        return False
                if not _CMP[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS and not node.keywords:
            return _FUNCS[node.func.id](*[ev(a) for a in node.args])
        if isinstance(node, ast.IfExp):
            return ev(node.body) if ev(node.test) else ev(node.orelse)
        raise ExpressionError(f"construct {type(node).__name__} not allowed in {expression!r}")

    return ev(tree)


def names(expression: str) -> set[str]:
    """Context names an expression needs (excluding rubric refs and literals)."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(expression, mode="eval")):
        if isinstance(node, ast.Attribute):
            d = _dotted(node)
            if d and not d.startswith("rubric."):
                out.add(d.split(".")[0])
        elif isinstance(node, ast.Name) and node.id not in ("true", "false", "null", "True", "False", "None"):
            out.add(node.id)
    out -= set(_FUNCS) | {"rubric"}
    return out
