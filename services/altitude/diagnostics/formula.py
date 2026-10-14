"""Safe evaluation of value-model formulas stored in the check catalogue.

Formulas are arithmetic over named variables only (detector signals, client inputs and rubric
factors), e.g. ``IDLE_CREDITS * recoverable_idle_share * price_per_credit * annualise``.
Numeric literals other than 0 and 1 are refused so factors cannot hide in formulas — they must be
rubric references (principle 1). Division by zero yields 0; missing/None operands count as 0.
"""

from __future__ import annotations

import ast
import operator
from typing import Any, Mapping

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: None}
_FUNCS = {"max": max, "min": min, "abs": abs}


class FormulaError(ValueError):
    pass


def _num(v: Any) -> float:
    if v is None:
        return 0.0
    if isinstance(v, bool):
        return float(v)
    return float(v)


def names(formula: str) -> set[str]:
    tree = _parse(formula)
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in _FUNCS}


def _parse(formula: str) -> ast.Expression:
    try:
        tree = ast.parse(formula, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"invalid formula {formula!r}: {e.msg}") from e
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)) or node.value not in (0, 1):
                raise FormulaError(f"formula {formula!r}: literal {node.value!r} not allowed; use a rubric factor")
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
                raise FormulaError(f"formula {formula!r}: only {sorted(_FUNCS)} calls are allowed")
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Name, ast.Load, ast.USub,
                                   ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Call)):
            raise FormulaError(f"formula {formula!r}: {type(node).__name__} not allowed")
    return tree


def evaluate(formula: str, variables: Mapping[str, Any]) -> float:
    tree = _parse(formula)

    def ev(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in variables:
                raise FormulaError(f"formula {formula!r}: unknown variable {node.id!r}")
            return _num(variables[node.id])
        if isinstance(node, ast.UnaryOp):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        if isinstance(node, ast.BinOp):
            a, b = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Div):
                return a / b if b else 0.0
            return _BIN[type(node.op)](a, b)
        if isinstance(node, ast.Call):
            return float(_FUNCS[node.func.id](*[ev(a) for a in node.args]))
        raise FormulaError(f"formula {formula!r}: unsupported node {type(node).__name__}")

    return ev(tree)
