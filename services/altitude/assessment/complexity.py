"""Complexity scoring (Section 16 / 32): LOC, procedural constructs, cursors,
dynamic SQL, control flow and known-issue hits, weighted and banded by
``rubric.assessment.complexity``.

Constructs are counted on code with comments and string literals blanked, so
commented-out code and SQL text inside literals never inflate the score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from altitude.core.rubric import RubricSet
from altitude_connectors.sqlrefs import blank_comments_and_strings

from .estate import Estate, EstateObject

_F = re.IGNORECASE | re.MULTILINE
CONSTRUCTS: dict[str, list[re.Pattern]] = {
    "cursor": [re.compile(p, _F) for p in (
        r"\bDECLARE\s+\w+\s+CURSOR\b", r"\bCURSOR\s+\w+\s+IS\b", r"\bAS\s+\w+\s+CURSOR\s+FOR\b",
        r"\bBULK\s+COLLECT\b")],
    "row_loop": [re.compile(p, _F) for p in (
        r"\bWHILE\b", r"(?<!END )\bLOOP\b", r"\bFOR\s+\w+\s+AS\b", r"\bFETCH\s+(?:NEXT\s+FROM\s+)?\w+")],
    "dynamic_sql": [re.compile(p, _F) for p in (
        r"\bsp_executesql\b", r"\bEXEC(?:UTE)?\s*\(", r"\bEXECUTE\s+IMMEDIATE\b", r"\bDBMS_SQL\b")],
    "error_handling": [re.compile(p, _F) for p in (
        r"\bBEGIN\s+TRY\b", r"\bRAISERROR\b", r"\bTHROW\b", r"@@ERROR\b", r"\bEXCEPTION\s+WHEN\b",
        r"\bRAISE\b", r"\bSIGNAL\b", r"@@ROWCOUNT\b", r"\bACTIVITYCOUNT\b", r"\bERRORCODE\b")],
    "control_flow": [re.compile(p, _F) for p in (
        r"(?<![.\w])IF\b", r"\bELSIF\b", r"\bGOTO\b", r"\bRETURN\b", r"\bCASE\s+WHEN\b")],
    "temp_table": [re.compile(p, _F) for p in (
        r"(?<![\w@])#\w+", r"\bVOLATILE\s+TABLE\b", r"\bGLOBAL\s+TEMPORARY\b")],
    "transaction": [re.compile(p, _F) for p in (
        r"\bBEGIN\s+TRAN(?:SACTION)?\b", r"\bCOMMIT\b", r"\bROLLBACK\b", r"\bAUTONOMOUS_TRANSACTION\b")],
    "bteq_control": [re.compile(p, _F) for p in (r"^\s*\.(?:IF|GOTO|LABEL)\b",)],
}
_PKG_SPEC = re.compile(r"PACKAGE\s+(?!BODY)[\w.]+\s+(?:AS|IS)\b(.*?)(?=\bPACKAGE\s+BODY\b|\Z)", re.IGNORECASE | re.DOTALL)
_PKG_VAR = re.compile(r"^\s*\w+\s+(?:CONSTANT\s+)?[A-Z_][\w.%]*(?:\(\d+(?:,\s*\d+)?\))?\s*(?::=[^;]*)?;", re.I | re.M)
_SUBPROGRAM = re.compile(r"^\s*(PROCEDURE|FUNCTION|END)\b", re.IGNORECASE | re.MULTILINE)


def count_constructs(text: str | None) -> dict[str, int]:
    if not text:
        return {}
    clean = blank_comments_and_strings(text)
    counts = {name: sum(len(p.findall(clean)) for p in pats) for name, pats in CONSTRUCTS.items()}
    m = _PKG_SPEC.search(clean)
    if m:
        spec = m.group(1)
        first_sub = _SUBPROGRAM.search(spec)
        head = spec[: first_sub.start()] if first_sub else spec
        counts["package_state"] = len(_PKG_VAR.findall(head))
    return {k: v for k, v in counts.items() if v}


@dataclass
class ComplexityResult:
    object_id: str
    score: float
    band: str
    factors: dict[str, Any]
    constructs: dict[str, int]


def _band(score: float, rubrics: RubricSet) -> str:
    if score >= float(rubrics.get("rubric.assessment.complexity.bands.high_min")):
        return "high"
    if score >= float(rubrics.get("rubric.assessment.complexity.bands.medium_min")):
        return "medium"
    return "low"


def score_object(obj: EstateObject, estate: Estate, rubrics: RubricSet,
                 drift_counts: dict[str, int] | None = None) -> ComplexityResult:
    weights = rubrics.get("rubric.assessment.complexity.weights")
    caps = rubrics.get("rubric.assessment.complexity.caps")
    constructs = count_constructs(obj.text)
    script_tasks = obj.attr_int("script_tasks") or 0
    if script_tasks:
        constructs["script_task"] = script_tasks
    quantities: dict[str, float] = {"loc_per_100": round(obj.loc / 100, 2)}
    quantities.update({k: float(v) for k, v in constructs.items()})
    for sev, n in sorted((drift_counts or {}).items()):
        key = {"S1": "known_issue_s1", "S2": "known_issue_s2"}.get(sev, "known_issue_other")
        quantities[key] = quantities.get(key, 0.0) + n
    fan_out = len({t for t, _ in estate.outbound.get(obj.object_id, [])})
    if fan_out:
        quantities["dependency_fan_out"] = float(fan_out)
    factors: dict[str, Any] = {}
    total = 0.0
    for name in sorted(quantities):
        qty = quantities[name]
        weight = float(weights.get(name, 0))
        points = qty * weight
        if name in caps:
            points = min(points, float(caps[name]))
        points = round(points, 2)
        if qty:
            factors[name] = {"quantity": qty, "weight": weight, "points": points}
        total += points
    score = round(min(total, float(rubrics.get("rubric.assessment.complexity.max_score"))), 2)
    return ComplexityResult(obj.object_id, score, _band(score, rubrics), factors, constructs)
