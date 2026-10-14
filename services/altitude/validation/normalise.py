"""Normalisation rules as data, rendered identically for both sides before aggregation and hashing.

Expressions are authored in DuckDB SQL (the in-boundary engine) and rendered for other
endpoints by :class:`~altitude.validation.endpoint.Endpoint` via sqlglot with
``unsupported_level=RAISE`` (so an engine that cannot express a rule fails loudly instead of
hashing something different).

A column's *comparison family* is the unification of its source and target families (e.g.
DATE vs TIMESTAMP compares as timestamp, INTEGER vs DECIMAL as decimal with the larger scale),
so canonical strings are comparable even when the migrated type differs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from altitude.core.ids import content_hash

from .config import NormRule, ValidationKnowledge, default_knowledge

_DEC = re.compile(r"^(DECIMAL|NUMERIC|NUMBER)\s*\(\s*(\d+)\s*(?:,\s*(\d+)\s*)?\)", re.I)


def family(dtype: str) -> str:
    t = (dtype or "").upper().strip()
    if re.match(r"^(TINYINT|SMALLINT|INTEGER|INT|BIGINT|HUGEINT|UTINYINT|USMALLINT|UINTEGER|UBIGINT|INT\d|BYTEINT)\b", t):
        return "integer"
    m = _DEC.match(t)
    if m:
        return "integer" if (m.group(3) in (None, "0")) and t.startswith("NUMBER") else "decimal"
    if re.match(r"^(DECIMAL|NUMERIC|NUMBER)\b", t):
        return "decimal"
    if re.match(r"^(DOUBLE|FLOAT|REAL)", t):
        return "float"
    if re.match(r"^(VARCHAR|CHAR|TEXT|STRING|NVARCHAR|NCHAR|BPCHAR)", t):
        return "string"
    if re.match(r"^(TIMESTAMP|DATETIME)", t):
        return "timestamp"
    if t == "DATE":
        return "date"
    if t in ("BOOLEAN", "BOOL"):
        return "boolean"
    return "other"


def scale_of(dtype: str) -> int:
    m = _DEC.match((dtype or "").strip())
    if m and m.group(3):
        return int(m.group(3))
    return 0


_NUMERIC = ("integer", "decimal")


def unify(src: str, tgt: str) -> str:
    """Comparison family for a source/target type pair."""
    if src == tgt:
        return src
    pair = {src, tgt}
    if pair <= set(_NUMERIC):
        return "decimal"
    if "float" in pair and pair <= {"float", *_NUMERIC}:
        return "float"
    if pair == {"date", "timestamp"}:
        return "timestamp"
    return "string"


@dataclass(frozen=True)
class ColumnPlan:
    name: str
    source_type: str
    target_type: str
    family: str          # comparison family
    scale: int           # canonical decimal scale (max of both sides)


@dataclass
class Normaliser:
    policies: tuple[str, ...] = ()
    knowledge: ValidationKnowledge = field(default_factory=default_knowledge)

    def __post_init__(self) -> None:
        unknown = set(self.policies) - set(self.knowledge.policies)
        if unknown:
            raise ValueError(f"unknown normalisation policies {sorted(unknown)}; known: {self.knowledge.policies}")
        self.policies = tuple(sorted(set(self.policies)))

    @property
    def applied(self) -> list[NormRule]:
        return [r for r in self.knowledge.rules if r.always or r.policy in self.policies]

    @property
    def version(self) -> str:
        """``normalisation_rule_version`` recorded on every validation run."""
        ident = [(r.id, r.op, r.params) for r in self.applied]
        return f"norm:{self.knowledge.normalisation_version}:{content_hash(ident, 10)}"

    def _rules_for(self, fam: str, value_level: bool) -> list[NormRule]:
        canonical = {"numeric_canonical", "float_canonical", "timestamp_canonical", "date_canonical",
                     "boolean_canonical"}
        return [r for r in self.applied if fam in r.applies_to and ((r.op not in canonical) == value_level)]

    def value_expr(self, col_sql: str, fam: str) -> str:
        """Policy rules applied to the typed value (still typed, not yet rendered)."""
        e = col_sql
        if fam == "string":
            e = f"CAST({e} AS VARCHAR)"
        for r in self._rules_for(fam, value_level=True):
            if r.op == "rtrim":
                e = f"rtrim({e})"
            elif r.op == "upper":
                e = f"upper({e})"
            elif r.op == "empty_as_null":
                e = f"nullif({e}, '')"
            elif r.op == "timestamp_precision":
                unit = {0: "second", 3: "millisecond", 6: "microsecond"}[int(r.params.get("fractional_digits", 6))]
                e = f"date_trunc('{unit}', {e})"
            elif r.op == "numeric_scale":
                e = f"round({e}, {int(r.params['scale'])})"
        return e

    def canonical_expr(self, plan: ColumnPlan, col_sql: str | None = None) -> str:
        """VARCHAR (or NULL) canonical rendering of a column, identical on both sides."""
        fam = plan.family
        v = self.value_expr(col_sql or _q(plan.name), fam)
        if fam in _NUMERIC:
            if plan.scale > 0:
                s = f"CAST(CAST({v} AS DECIMAL(38, {plan.scale})) AS VARCHAR)"
                return f"CASE WHEN {v} IS NULL THEN NULL ELSE rtrim(rtrim({s}, '0'), '.') END"
            return f"CAST(CAST({v} AS DECIMAL(38, 0)) AS VARCHAR)"
        if fam == "float":
            digits = int(next((r.params.get("significant_digits", 15) for r in self.applied
                               if r.op == "float_canonical"), 15))
            return f"printf('%.{digits}g', CAST({v} AS DOUBLE))"
        if fam == "timestamp":
            return f"strftime(CAST({v} AS TIMESTAMP), '%Y-%m-%d %H:%M:%S.%f')"
        if fam == "date":
            return f"strftime(CAST({v} AS DATE), '%Y-%m-%d')"
        if fam == "boolean":
            return f"CASE WHEN {v} IS NULL THEN NULL WHEN {v} THEN 'true' ELSE 'false' END"
        return f"CAST({v} AS VARCHAR)"


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def encode(expr: str) -> str:
    """Null-safe, length-prefixed encoding so ('a|b', NULL) never collides with ('a', 'b')."""
    return f"coalesce('V' || CAST(length({expr}) AS VARCHAR) || ':' || {expr}, 'N')"


def row_expr(normaliser: Normaliser, plans: list[ColumnPlan]) -> str:
    return " || ".join(encode(normaliser.canonical_expr(p)) for p in plans) if plans else "''"
