"""Anti-pattern detector (Section 31) driven by ``knowledge/anti_patterns/*.yaml``.

Each catalogue entry names an executable detector in :data:`DETECTORS`, the
object types it applies to, a rubric reference for credits per affected run
and whether the impact scales with table size. Estimated monthly credit impact
= runs per month x credits per run x size factor (all factors from
``rubric.assessment.anti_patterns``) — an estimate with its method recorded,
not a measurement.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from altitude.core.ids import stable_id
from altitude.core.knowledge import load_entries
from altitude.core.rubric import RubricSet
from altitude_connectors.sqlrefs import blank_comments_and_strings

from .estate import Estate, EstateObject

_I = re.IGNORECASE
_SNIPPET_CHARS = 160


@dataclass
class Finding:
    offset: int
    evidence: dict[str, Any] = field(default_factory=dict)
    target: str | None = None  # object id whose size drives the impact


@dataclass
class Ctx:
    obj: EstateObject
    estate: Estate
    rubrics: RubricSet
    raw: str
    clean: str
    entry: dict[str, Any]


def _statements(clean: str) -> list[tuple[int, str]]:
    out, start = [], 0
    for m in re.finditer(r";|\n\s*\n", clean):
        out.append((start, clean[start:m.start()]))
        start = m.end()
    out.append((start, clean[start:]))
    return [(o, s) for o, s in out if s.strip()]


def _table_rows(estate: Estate, oid: str) -> tuple[int | None, int | None]:
    o = estate.objects.get(oid)
    return (o.attr_int("row_count"), o.attr_int("size_bytes")) if o else (None, None)


def _is_large(estate: Estate, oid: str, rubrics: RubricSet) -> bool:
    rows, size = _table_rows(estate, oid)
    if rows is not None:
        return rows >= int(rubrics.get("rubric.assessment.anti_patterns.large_table_rows_min"))
    if size is not None:
        return size >= int(rubrics.get("rubric.assessment.anti_patterns.large_table_bytes_min"))
    return False


# --------------------------------------------------------------------------- detectors


def detect_row_by_row(c: Ctx) -> list[Finding]:
    loops = [m for p in (r"\bDECLARE\s+\w+\s+CURSOR\b", r"\bCURSOR\s+\w+\s+IS\b", r"\bAS\s+\w+\s+CURSOR\s+FOR\b",
                         r"\bWHILE\b", r"(?<!END )\bLOOP\b") for m in re.finditer(p, c.clean, _I)]
    if not loops:
        return []
    first = min(loops, key=lambda m: m.start())
    after = c.clean[first.start():]
    dml = re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|INS|UPD|DEL)\b", after, _I)
    if not dml:
        return []
    targets = c.estate.writes(c.obj.object_id) or c.estate.reads(c.obj.object_id)
    return [Finding(first.start(), {"loop": first.group(0).strip(), "dml": dml.group(1).upper()},
                    _largest(c.estate, targets))]


def detect_select_star(c: Ctx) -> list[Finding]:
    pipeline = c.obj.object_type in {"view", "etl_job"} or bool(c.estate.writes(c.obj.object_id))
    if not pipeline:
        return []
    out = []
    for m in re.finditer(r"\bSELECT\s+(?:DISTINCT\s+)?(?:TOP\s+\d+\s+)?(?:\w+\.)?\*", c.clean, _I):
        before = c.clean[max(0, m.start() - 12):m.start()]
        if re.search(r"EXISTS\s*\(\s*$", before, _I):
            continue
        out.append(Finding(m.start(), {"statement": "SELECT *"}))
    return out[:1] if out else []


def detect_full_reload(c: Ctx) -> list[Finding]:
    out = []
    for oid in c.estate.writes(c.obj.object_id):
        short = re.escape(c.estate.name(oid).split(".")[-1])
        wipe = re.search(rf"\bTRUNCATE\s+TABLE\s+[\w.\[\]\"]*{short}\b|\bDEL(?:ETE)?\s+(?:FROM\s+)?[\w.\[\]\"]*{short}\b"
                         rf"(?:\s+ALL\b)?\s*(?:;|$|\n)", c.clean, _I | re.MULTILINE)
        if not wipe:
            continue
        reload_ = re.search(rf"\bINS(?:ERT)?\s+(?:INTO\s+)?[\w.\[\]\"]*{short}\b", c.clean[wipe.end():], _I)
        if reload_ and _is_large(c.estate, oid, c.rubrics):
            rows, size = _table_rows(c.estate, oid)
            out.append(Finding(wipe.start(), {"table": c.estate.name(oid), "row_count": rows, "size_bytes": size}, oid))
    return out


def detect_nested_views(c: Ctx) -> list[Finding]:
    depth = c.estate.view_depth(c.obj.object_id)
    limit = int(c.rubrics.get(c.entry["threshold_ref"]))
    if depth > limit:
        m = re.search(r"\bFROM\b", c.clean, _I)
        return [Finding(m.start() if m else 0, {"depth": depth, "limit": limit})]
    return []


def detect_cross_join(c: Ctx) -> list[Finding]:
    out = []
    for off, stmt in _statements(c.clean):
        m = re.search(r"\bCROSS\s+JOIN\b", stmt, _I)
        if m:
            out.append(Finding(off + m.start(), {"form": "CROSS JOIN"}))
            continue
        frm = re.search(r"\bFROM\b(.*?)(?=\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|\bHAVING\b|\bUNION\b|\bINTO\b|\Z)",
                        stmt, _I | re.S)
        if not frm or re.search(r"\bWHERE\b", stmt[frm.end():], _I):
            continue
        if not re.search(r"\b(SELECT|SEL|DELETE|DEL|UPDATE|UPD)\b", stmt[:frm.start()], _I) or \
                re.search(r"\bFETCH\b", stmt[:frm.start()], _I):
            continue
        depth, comma = 0, False
        for ch in frm.group(1):
            depth += ch == "("
            depth -= ch == ")"
            if ch == "," and depth == 0:
                comma = True
        if comma and not re.search(r"\bJOIN\b", frm.group(1), _I):
            out.append(Finding(off + frm.start(), {"form": "comma join without predicate"}))
    targets = c.estate.reads(c.obj.object_id)
    for f in out:
        f.target = _largest(c.estate, targets)
    return out


_FUNCS = (r"YEAR|MONTH|DAY|UPPER|LOWER|CONVERT|CAST|ISNULL|NVL|COALESCE|SUBSTRING|SUBSTR|TRUNC|DATEPART|"
          r"LTRIM|RTRIM|TRIM|DATEADD|TO_CHAR|FORMAT|LEFT|RIGHT")
_CALL = r"\((?:[^()]|\([^()]*\))*\)"


def detect_non_sargable(c: Ctx) -> list[Finding]:
    out = []
    for clause in re.finditer(r"\b(WHERE|ON|AND|OR)\b", c.clean, _I):
        seg = c.clean[clause.end():clause.end() + 200]
        m = re.match(rf"\s*\(?\s*(?:{_FUNCS})\s*{_CALL}\s*(=|<>|!=|<=|>=|<|>|\bIN\b|\bLIKE\b|\bBETWEEN\b)", seg, _I)
        if m:
            out.append(Finding(clause.end() + m.start(), {"form": "function on filtered column"}))
            continue
        m = re.match(r"\s*\(?\s*[A-Za-z_][\w.]*\s*[-+*/]\s*\w+\s*(=|<>|<=|>=|<|>)", seg, _I)
        if m and clause.group(1).upper() in {"WHERE", "AND", "OR"}:
            out.append(Finding(clause.end() + m.start(), {"form": "arithmetic on filtered column"}))
    for m in re.finditer(r"\bLIKE\s+N?'{1,2}%", c.raw, _I):
        out.append(Finding(m.start(), {"form": "leading-wildcard LIKE"}))
    targets = c.estate.reads(c.obj.object_id)
    big = _largest(c.estate, targets)
    seen, uniq = set(), []
    for f in sorted(out, key=lambda f: f.offset):
        if f.offset not in seen:
            seen.add(f.offset)
            f.target = big
            uniq.append(f)
    return uniq


def detect_unnecessary_distinct(c: Ctx) -> list[Finding]:
    out = []
    for off, stmt in _statements(c.clean):
        d = re.search(r"\bSELECT\s+DISTINCT\b", stmt, _I)
        if d and re.search(r"\bGROUP\s+BY\b", stmt[d.end():], _I):
            out.append(Finding(off + d.start(), {"form": "DISTINCT with GROUP BY"}))
            continue
        for m in re.finditer(r"\b(IN|EXISTS)\s*\(\s*SELECT\s+DISTINCT\b", stmt, _I):
            out.append(Finding(off + m.start(), {"form": f"DISTINCT inside {m.group(1).upper()}"}))
        if d and re.search(r"\bUNION\b(?!\s+ALL)", stmt, _I):
            out.append(Finding(off + d.start(), {"form": "DISTINCT before UNION"}))
    return out


def detect_wide_variant(c: Ctx) -> list[Finding]:
    wide = {str(t).lower() for t in c.rubrics.get("rubric.assessment.anti_patterns.wide_column_types")}
    star = re.search(r"\bSELECT\s+(?:DISTINCT\s+)?(?:\w+\.)?\*", c.clean, _I)
    if not star:
        return []
    out = []
    for oid in c.estate.reads(c.obj.object_id):
        cols = [col for col in c.estate.objects[oid].columns
                if col["data_type"].lower() in wide or col["data_type"].lower().split("(")[0] in wide]
        if cols:
            out.append(Finding(star.start(), {"table": c.estate.name(oid), "columns": [x["column_name"] for x in cols]},
                               oid))
    return out


def _largest(estate: Estate, oids: list[str]) -> str | None:
    best, best_key = None, (-1, -1)
    for oid in oids:
        rows, size = _table_rows(estate, oid)
        key = (rows if rows is not None else -1, size if size is not None else -1)
        if key > best_key:
            best, best_key = oid, key
    return best


DETECTORS: dict[str, Callable[[Ctx], list[Finding]]] = {
    "row_by_row": detect_row_by_row,
    "select_star_pipeline": detect_select_star,
    "full_reload": detect_full_reload,
    "nested_views": detect_nested_views,
    "cross_join": detect_cross_join,
    "non_sargable": detect_non_sargable,
    "unnecessary_distinct": detect_unnecessary_distinct,
    "wide_variant_scan": detect_wide_variant,
}


# --------------------------------------------------------------------------- catalogue and impact


def load_catalogue(root: Path | None = None) -> list[dict[str, Any]]:
    entries = load_entries("anti_patterns/*.yaml", "anti_patterns", root)
    for e in entries:
        if e["detector"] not in DETECTORS:
            raise ValueError(f"{e['_source']}: {e['id']} names unknown detector {e['detector']!r}")
    return sorted(entries, key=lambda e: e["id"])


class ImpactModel:
    """runs/month x credits/run x size factor; every input is evidence or rubric data."""

    def __init__(self, estate: Estate, rubrics: RubricSet):
        self.estate = estate
        self.rubrics = rubrics
        self._runs: dict[str, float] = {}

    def runs_per_month(self, oid: str, _seen: frozenset = frozenset()) -> float:
        if oid in self._runs:
            return self._runs[oid]
        months = float(self.rubrics.get("rubric.assessment.anti_patterns.usage_months"))
        obj = self.estate.objects[oid]
        if obj.usage_90d:
            runs = obj.usage_90d / months
        else:
            runs = sum(self.runs_per_month(c, _seen | {oid}) for c in self.estate.consumers(oid) if c not in _seen)
        self._runs[oid] = runs  # evaluation order is deterministic (sorted object ids)
        return runs

    def size_factor(self, target: str | None) -> float:
        if not target:
            return 1.0
        rows, size = _table_rows(self.estate, target)
        ap = "rubric.assessment.anti_patterns."
        if rows is not None:
            return max(1.0, rows / float(self.rubrics.get(ap + "rows_per_size_unit")))
        if size is not None:
            return max(1.0, size / float(self.rubrics.get(ap + "bytes_per_size_unit")))
        return 1.0

    def credits(self, oid: str, entry: dict[str, Any], target: str | None) -> dict[str, Any]:
        runs = self.runs_per_month(oid)
        per_run = float(self.rubrics.get(entry["credits_per_run_ref"]))
        factor = self.size_factor(target) if entry.get("size_sensitive") else 1.0
        credits = round(runs * per_run * factor, 4)
        price = float(self.rubrics.get("rubric.assessment.anti_patterns.credit_price_usd"))
        return {"runs_per_month": round(runs, 2), "credits_per_run": per_run, "size_factor": round(factor, 3),
                "credits_month": credits, "usd_month": round(credits * price, 2),
                "method": "runs_per_month x credits_per_run x size_factor"}


def detect(estate: Estate, rubrics: RubricSet, catalogue: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    catalogue = catalogue if catalogue is not None else load_catalogue()
    impact = ImpactModel(estate, rubrics)
    hits: list[dict[str, Any]] = []
    for oid in sorted(estate.objects):
        obj = estate.objects[oid]
        if not obj.text and obj.object_type != "view":
            continue
        raw = obj.text or ""
        clean = blank_comments_and_strings(raw)
        for entry in catalogue:
            if obj.object_type not in entry["applies_to"]:
                continue
            for f in DETECTORS[entry["detector"]](Ctx(obj, estate, rubrics, raw, clean, entry)):
                line = raw.count("\n", 0, f.offset) + 1
                snippet = raw.splitlines()[line - 1].strip()[:_SNIPPET_CHARS] if raw else ""
                money = impact.credits(oid, entry, f.target)
                hits.append({
                    "hit_id": stable_id("APH", oid, entry["id"], line),
                    "object_id": oid, "fq_name": obj.fq_name, "pattern_id": entry["id"], "pattern": entry["name"],
                    "severity": entry["severity"], "line": line, "snippet": snippet,
                    "evidence": dict(f.evidence), "target_object_id": f.target,
                    "credits_month": money["credits_month"], "usd_month": money["usd_month"], "impact": money,
                    "recommendation": " ".join(entry["recommendation"].split()),
                })
    uniq = {h["hit_id"]: h for h in hits}
    return [uniq[k] for k in sorted(uniq)]
