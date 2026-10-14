#!/usr/bin/env python3
"""CI lint: no numeric thresholds in application code (principle 1).

Thresholds, weights and factors belong in ``knowledge/rubrics`` and are read by
reference. This lint flags, in application code:

1. comparisons against a numeric literal other than the neutral values
   (0, 1, -1, 0.0, 1.0);
2. numeric literals assigned (or defaulted, or passed as keyword arguments) to
   names that look like thresholds (threshold, limit, cutoff, tolerance,
   min/max, confidence, ratio, pct, rate, weight, factor).

Escape hatches (must carry a reason):
- line pragma:   ``# threshold-ok: <reason>``
- file pragma:   ``# lint: thresholds-exempt (<reason>)`` within the first 10 lines
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOTS = ["services", "agents", "connectors"]
NEUTRAL = {0, 1, -1}
NAME_RE = re.compile(
    r"(threshold|limit|cutoff|tolerance|(^|_)min($|_)|(^|_)max($|_)|confidence|ratio|pct|percent|rate|weight|factor)",
    re.IGNORECASE,
)
LINE_PRAGMA = re.compile(r"#\s*threshold-ok:\s*\S")
FILE_PRAGMA = re.compile(r"#\s*lint:\s*thresholds-exempt\s*\(.+\)")


def _is_num(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool)


def _num(node: ast.AST) -> float:
    if isinstance(node, ast.UnaryOp):
        return -node.operand.value  # type: ignore[attr-defined]
    return node.value  # type: ignore[attr-defined]


def _target_names(t: ast.AST) -> list[str]:
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, ast.Attribute):
        return [t.attr]
    if isinstance(t, (ast.Tuple, ast.List)):
        return [n for e in t.elts for n in _target_names(e)]
    return []


def lint_source(src: str, filename: str) -> list[str]:
    lines = src.splitlines()
    if any(FILE_PRAGMA.search(l) for l in lines[:10]):
        return []
    try:
        tree = ast.parse(src, filename)
    except SyntaxError as e:
        return [f"{filename}:{e.lineno}: syntax error: {e.msg}"]
    problems: list[str] = []

    def flag(node: ast.AST, msg: str) -> None:
        ln = getattr(node, "lineno", 0)
        if 0 < ln <= len(lines) and LINE_PRAGMA.search(lines[ln - 1]):
            return
        problems.append(f"{filename}:{ln}: {msg}")

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            for op, (a, b) in zip(node.ops, zip(operands, operands[1:])):
                if isinstance(op, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    for side in (a, b):
                        if _is_num(side) and _num(side) not in NEUTRAL:
                            flag(node, f"numeric literal {_num(side)!r} in comparison; use a rubric reference")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            if value is not None and _is_num(value) and _num(value) not in NEUTRAL:
                for name in (n for t in targets for n in _target_names(t)):
                    if NAME_RE.search(name):
                        flag(node, f"threshold-like name {name!r} assigned literal {_num(value)!r}")
        elif isinstance(node, ast.keyword):
            if node.arg and NAME_RE.search(node.arg) and _is_num(node.value) and _num(node.value) not in NEUTRAL:
                flag(node.value, f"threshold-like keyword {node.arg!r}={_num(node.value)!r}")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            positional = args.posonlyargs + args.args
            for arg, default in zip(positional[len(positional) - len(args.defaults):], args.defaults):
                if NAME_RE.search(arg.arg) and _is_num(default) and _num(default) not in NEUTRAL:
                    flag(default, f"threshold-like parameter {arg.arg!r} defaults to {_num(default)!r}")
            for arg, default in zip(args.kwonlyargs, args.kw_defaults):
                if default is not None and NAME_RE.search(arg.arg) and _is_num(default) and _num(default) not in NEUTRAL:
                    flag(default, f"threshold-like parameter {arg.arg!r} defaults to {_num(default)!r}")
    return problems


def iter_files(root: Path) -> list[Path]:
    files = []
    for r in ROOTS:
        base = root / r
        if base.exists():
            files.extend(p for p in base.rglob("*.py") if ".venv" not in p.parts)
    return sorted(files)


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    problems = []
    for f in iter_files(root):
        problems.extend(lint_source(f.read_text(), str(f.relative_to(root))))
    for p in problems:
        print(p)
    print(f"lint_thresholds: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
