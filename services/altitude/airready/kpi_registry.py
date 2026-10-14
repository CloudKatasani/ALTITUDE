"""Certified KPI registry (Section 26) and the semantic view generator (Section 15.2 AI pack).

**One definition per KPI** is enforced here: every KPI name and synonym (compared case- and
punctuation-insensitively) must resolve to exactly one KPI across the registry. A conflicting definition
raises :class:`KPIDefinitionConflict` naming both KPIs, their expressions and their file:line locations,
and no semantic view is generated.

Semantic views are rendered as Snowflake ``CREATE SEMANTIC VIEW`` DDL (TABLES / RELATIONSHIPS / FACTS /
DIMENSIONS / METRICS), one per domain, from certified KPIs only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import sqlglot
import yaml

from altitude.core.errors import KnowledgeValidationError
from altitude.core.ids import content_hash
from altitude.core.paths import knowledge_dir

REL = "semantic/kpi_registry.yaml"
MEMBER_RE = re.compile(r"\b([a-z][a-z0-9_]*)\.([a-z][a-z0-9_]*)\b")


class KPIDefinitionConflict(KnowledgeValidationError):
    """Two KPI definitions claim the same KPI name or synonym."""


def norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def snake(text: str) -> str:
    return norm(text).replace(" ", "_")


def _lines(text: str) -> dict[tuple, int]:
    out: dict[tuple, int] = {}

    def walk(node: yaml.Node, path: tuple) -> None:
        out.setdefault(path, node.start_mark.line + 1)
        if isinstance(node, yaml.MappingNode):
            for k, v in node.value:
                out[path + (k.value,)] = k.start_mark.line + 1
                walk(v, path + (k.value,))
        elif isinstance(node, yaml.SequenceNode):
            for i, v in enumerate(node.value):
                walk(v, path + (i,))

    root = yaml.compose(text)
    if root is not None:
        walk(root, ())
    return out


@dataclass
class Registry:
    doc: dict
    rel: str = REL

    @property
    def domains(self) -> dict[str, dict]:
        return {d["name"]: d for d in self.doc["domains"]}

    @property
    def kpis(self) -> dict[str, dict]:
        return {k["id"]: k for k in self.doc["kpis"]}

    @property
    def version(self) -> str:
        return "KPI-" + content_hash(self.doc, 12).upper()

    def names(self) -> list[str]:
        """Lower-cased certified KPI names and synonyms (the glossary)."""
        out = set()
        for k in self.doc["kpis"]:
            if k["certified"]:
                out.add(k["name"].lower())
                out.update(s.lower() for s in k["synonyms"])
        return sorted(out)

    def member(self, domain: str, alias: str, name: str) -> dict | None:
        d = self.domains[domain]
        return next((m for m in d["facts"] + d["dimensions"] if m["table"] == alias and m["name"] == name), None)

    def translate(self, domain: str, expression: str) -> str:
        """``SUM(orders.net_amount)`` -> ``SUM(orders.NET_AMOUNT)`` (physical column expressions)."""
        def sub(m: re.Match) -> str:
            mem = self.member(domain, m.group(1), m.group(2))
            return f"{m.group(1)}.{mem['expr']}" if mem else m.group(0)
        return MEMBER_RE.sub(sub, expression)


def validate(doc: dict, text: str | None = None, rel: str = REL) -> list[str]:
    """Problems with precise locations; conflicts are prefixed ``KPI conflict``."""
    lines = _lines(text) if text else {}

    def at(*path: object) -> str:
        for cut in range(len(path), -1, -1):
            if tuple(path[:cut]) in lines:
                return f"{rel}:{lines[tuple(path[:cut])]}"
        return rel

    problems: list[str] = []
    domains = {d["name"]: d for d in doc.get("domains", [])}
    for di, d in enumerate(doc.get("domains", [])):
        aliases = {t["alias"] for t in d["tables"]}
        seen: set[str] = set()
        for kind in ("facts", "dimensions"):
            for mi, m in enumerate(d[kind]):
                if m["table"] not in aliases:
                    problems.append(f"{at('domains', di, kind, mi)}: {d['name']}.{m['name']}: unknown table alias {m['table']!r}")
                key = f"{m['table']}.{m['name']}"
                if key in seen:
                    problems.append(f"{at('domains', di, kind, mi)}: {d['name']}: duplicate member {key}")
                seen.add(key)
        for ri, r in enumerate(d["relationships"]):
            for side in ("from", "to"):
                if r[side] not in aliases:
                    problems.append(f"{at('domains', di, 'relationships', ri)}: relationship {r['name']}: unknown alias {r[side]!r}")

    registry = Registry(doc)
    claims: dict[str, tuple[int, dict, str]] = {}
    for ki, k in enumerate(doc.get("kpis", [])):
        d = domains.get(k["domain"])
        if d is None:
            problems.append(f"{at('kpis', ki, 'domain')}: {k['id']}: unknown domain {k['domain']!r}")
            continue
        if k["table"] not in {t["alias"] for t in d["tables"]}:
            problems.append(f"{at('kpis', ki, 'table')}: {k['id']}: unknown table alias {k['table']!r} in {d['name']}")
        for alias, name in MEMBER_RE.findall(k["expression"]):
            if registry.member(k["domain"], alias, name) is None:
                problems.append(f"{at('kpis', ki, 'expression')}: {k['id']}: expression references unknown member "
                                f"{alias}.{name} in domain {d['name']}")
        try:
            sqlglot.parse_one(f"SELECT {registry.translate(k['domain'], k['expression'])}", read="snowflake")
        except sqlglot.errors.ParseError as e:
            problems.append(f"{at('kpis', ki, 'expression')}: {k['id']}: expression does not parse: {e}")
        members = {m["name"] for m in d["facts"] + d["dimensions"]} | {t["alias"] for t in d["tables"]}
        if snake(k["name"]) in members:
            problems.append(f"{at('kpis', ki, 'name')}: {k['id']}: metric name {snake(k['name'])!r} collides with a "
                            f"table alias, fact or dimension in {d['name']}")
        for label in [k["name"], *k["synonyms"]]:
            key = norm(label)
            if key in claims and claims[key][1]["id"] != k["id"]:
                oi, other, _ = claims[key]
                problems.append(
                    f"KPI conflict: {at('kpis', ki, 'name')}: {label!r} is defined twice — {k['id']} "
                    f"({k['expression']}) conflicts with {other['id']} ({other['expression']}) at {at('kpis', oi, 'name')}; "
                    "one definition per KPI")
            claims.setdefault(key, (ki, k, label))
    return problems


def load(root: Path | None = None, rel: str = REL, strict: bool = True) -> Registry:
    root = root or knowledge_dir()
    text = (root / rel).read_text()
    doc = yaml.safe_load(text)
    if strict:
        problems = validate(doc, text, rel)
        if problems:
            cls = KPIDefinitionConflict if any(p.startswith("KPI conflict") for p in problems) else KnowledgeValidationError
            raise cls(problems)
    return Registry(doc, rel)


def from_text(text: str, rel: str = REL) -> Registry:
    doc = yaml.safe_load(text)
    problems = validate(doc, text, rel)
    if problems:
        cls = KPIDefinitionConflict if any(p.startswith("KPI conflict") for p in problems) else KnowledgeValidationError
        raise cls(problems)
    return Registry(doc, rel)


# --------------------------------------------------------------------------- semantic view DDL
def _q(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _syn(items: list[str]) -> str:
    return f" WITH SYNONYMS = ({', '.join(_q(s) for s in items)})" if items else ""


def render_semantic_view(registry: Registry, domain: str) -> str:
    d = registry.domains[domain]
    kpis = [k for k in registry.doc["kpis"] if k["domain"] == domain and k["certified"]]
    pk = {t["alias"]: t["primary_key"] for t in d["tables"]}
    tables = [f"    {t['alias']} AS {t['table']} PRIMARY KEY ({', '.join(t['primary_key'])})"
              f"{_syn(t.get('synonyms', []))} COMMENT = {_q(t['description'])}" for t in d["tables"]]
    rels = [f"    {r['name']} AS {r['from']} ({', '.join(r['columns'])}) REFERENCES {r['to']} ({', '.join(pk[r['to']])})"
            for r in d["relationships"]]
    facts = [f"    {m['table']}.{m['name']} AS {m['expr']}{_syn(m.get('synonyms', []))} COMMENT = {_q(m['description'])}"
             for m in d["facts"]]
    dims = [f"    {m['table']}.{m['name']} AS {m['expr']}{_syn(m.get('synonyms', []))} COMMENT = {_q(m['description'])}"
            for m in d["dimensions"]]
    metrics = []
    for k in kpis:
        comment = f"[{k['id']}] {k['description']} Owner: {k['owner']}"
        metrics.append(f"    {k['table']}.{snake(k['name'])} AS {k['expression']}{_syn(k['synonyms'])} "
                       f"COMMENT = {_q(comment)}")
    parts = [f"CREATE OR REPLACE SEMANTIC VIEW {d['semantic_view']}", "  TABLES (", ",\n".join(tables), "  )"]
    if rels:
        parts += ["  RELATIONSHIPS (", ",\n".join(rels), "  )"]
    if facts:
        parts += ["  FACTS (", ",\n".join(facts), "  )"]
    if dims:
        parts += ["  DIMENSIONS (", ",\n".join(dims), "  )"]
    parts += ["  METRICS (", ",\n".join(metrics), "  )", f"  COMMENT = {_q(d['description'] + ' Owner: ' + d['owner'])};"]
    return "\n".join(parts) + "\n"


def semantic_views(registry: Registry | None = None) -> dict[str, str]:
    """{domain: DDL}. Loading the registry enforces one definition per KPI first."""
    registry = registry or load()
    return {name: render_semantic_view(registry, name) for name in sorted(registry.domains)}


def validate_tree(root: Path) -> list[str]:
    """Hook for ``altitude knowledge validate``: one definition per KPI across the registry."""
    path = root / REL
    if not path.exists():
        return []
    text = path.read_text()
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError:
        return []  # reported by the schema pass
    return validate(doc or {}, text, REL)
