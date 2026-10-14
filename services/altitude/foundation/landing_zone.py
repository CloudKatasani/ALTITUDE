"""Landing-zone model (Section 15.2): load, expand and semantically validate ``knowledge/foundation``.

The YAML is schema-checked by the knowledge validator; this module adds the cross-reference rules a JSON
schema cannot express (every referenced role, warehouse, tag, rule and policy exists; users only receive
functional roles; warehouse settings are inside the compute rubric) and expands the role model:

    database  = <ENV>_<DOMAIN>_<LAYER>
    access    = AR_<database>_RO / AR_<database>_RW   (object privileges, future grants)
    functional= FR_*                                   (granted access roles + warehouses)
    users     -> functional roles only
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from altitude.core.errors import KnowledgeValidationError
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics

SOURCE = "knowledge/foundation/landing_zone.yaml"


@dataclass(frozen=True)
class Database:
    name: str
    env: str
    domain: str
    layer: str
    retention_days: int
    managed_access: bool
    owner: str
    cost_center: str


@dataclass
class LandingZone:
    doc: dict
    databases: list[Database] = field(default_factory=list)
    access_roles: dict[str, tuple[str, str]] = field(default_factory=dict)        # role -> (database, level)
    functional_access: dict[str, list[str]] = field(default_factory=dict)        # FR -> [AR...]
    agent_identities: list[dict] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        return self.doc[key]

    @property
    def warehouses(self) -> list[dict]:
        return self.doc["warehouses"]

    def access_role(self, database: str, level: str) -> str:
        return self.doc["naming"]["access_role_pattern"].format(database=database, level=level)


def _expand(doc: dict, root: Path | None) -> LandingZone:
    lz = LandingZone(doc)
    envs = {e["name"]: e for e in doc["environments"]}
    for env in doc["environments"]:
        for dom in doc["domains"]:
            for layer in doc["layers"]:
                name = doc["naming"]["database_pattern"].format(env=env["name"], domain=dom["name"], layer=layer["name"])
                lz.databases.append(Database(name, env["name"], dom["name"], layer["name"], layer["retention_days"],
                                             envs[env["name"]]["managed_access"], dom["owner"], dom["cost_center"]))
    for db in lz.databases:
        for level in ("RO", "RW"):
            lz.access_roles[lz.access_role(db.name, level)] = (db.name, level)
    for fr in doc["functional_roles"]:
        granted: list[str] = []
        for g in fr["access"]:
            for db in lz.databases:
                if all(fnmatch.fnmatchcase(getattr(db, k), g[k]) for k in ("env", "domain", "layer")):
                    role = lz.access_role(db.name, g["level"])
                    if role not in granted:
                        granted.append(role)
        lz.functional_access[fr["name"]] = granted
    agents_cfg = doc["agents"]
    cat = load_yaml(agents_cfg["source"], root)
    for a in cat["agents"]:
        if agents_cfg["include"] == "all" or a.get("implemented"):
            ident = a["service_identity"]
            lz.agent_identities.append({"agent_id": a["id"], "name": a["name"], "user": ident["user"],
                                        "role": ident["role"], "warehouse": agents_cfg["warehouse"]})
    return lz


def validate(lz: LandingZone, rubrics: RubricSet | None = None) -> list[str]:
    """Return precise problems (empty when the landing zone is sound)."""
    rubrics = rubrics or default_rubrics()
    d = lz.doc
    problems: list[str] = []
    regex = re.compile(d["naming"]["database_regex"])
    for db in lz.databases:
        if not regex.match(db.name):
            problems.append(f"database {db.name} does not match naming regex {d['naming']['database_regex']}")
    whs = {w["name"] for w in d["warehouses"]}
    frs = {f["name"] for f in d["functional_roles"]}
    tags = {t["name"] for t in d["governance"]["tags"]}
    rules = {r["name"] for r in d["network"]["rules"]}
    policies = {p["name"] for p in d["network"]["policies"]}
    for fr in d["functional_roles"]:
        if not lz.functional_access[fr["name"]]:
            problems.append(f"functional role {fr['name']}: access patterns match no database")
        for w in fr["warehouses"]:
            if w not in whs:
                problems.append(f"functional role {fr['name']}: unknown warehouse {w}")
    for u in d["users"]:
        for r in u["functional_roles"]:
            if r not in frs:
                problems.append(f"user {u['name']}: unknown functional role {r} (users receive functional roles only)")
        if u.get("default_warehouse") and u["default_warehouse"] not in whs:
            problems.append(f"user {u['name']}: unknown default warehouse {u['default_warehouse']}")
        if u.get("network_policy") and u["network_policy"] not in policies:
            problems.append(f"user {u['name']}: unknown network policy {u['network_policy']}")
    max_suspend = rubrics.get("rubric.compute.auto_suspend_max_seconds")
    max_timeout = rubrics.get("rubric.compute.statement_timeout_max_seconds")
    classes = set(rubrics.get("rubric.compute.allowed_workload_classes"))
    max_pct = rubrics.get("rubric.foundation.monitor_suspend_at_max_pct")
    for w in d["warehouses"]:
        if w["auto_suspend"] > max_suspend:
            problems.append(f"warehouse {w['name']}: auto_suspend {w['auto_suspend']}s exceeds "
                            f"rubric.compute.auto_suspend_max_seconds ({max_suspend})")
        if w["statement_timeout_seconds"] > max_timeout:
            problems.append(f"warehouse {w['name']}: statement timeout exceeds rubric.compute.statement_timeout_max_seconds")
        if w["workload_class"] not in classes:
            problems.append(f"warehouse {w['name']}: unknown workload class {w['workload_class']}")
        if w["min_clusters"] > w["max_clusters"]:
            problems.append(f"warehouse {w['name']}: min_clusters > max_clusters")
        if w["monitor"]["suspend_at"] > max_pct:
            problems.append(f"warehouse {w['name']}: monitor suspends at {w['monitor']['suspend_at']}% (> {max_pct}%)")
    if d["agents"]["warehouse"] not in whs:
        problems.append(f"agents: unknown warehouse {d['agents']['warehouse']}")
    for p in d["network"]["policies"]:
        for r in p["allowed_rules"]:
            if r not in rules:
                problems.append(f"network policy {p['name']}: unknown rule {r}")
    if sum(1 for p in d["network"]["policies"] if p["account_default"]) != 1:
        problems.append("network: exactly one policy must be the account default")
    for m in d["governance"]["masking"]:
        if m["tag"] not in tags:
            problems.append(f"masking policy {m['name']}: unknown tag {m['tag']}")
        for r in m["unmasked_roles"]:
            if r not in frs:
                problems.append(f"masking policy {m['name']}: unknown role {r}")
    for b in d["budgets"]:
        for o in b.get("objects", []):
            if o not in whs:
                problems.append(f"budget {b['name']}: unknown object {o}")
    for a in lz.agent_identities:
        if a["role"] in lz.access_roles or a["role"] in frs:
            problems.append(f"agent {a['agent_id']}: role {a['role']} must be a distinct agent role")
    return problems


def load(root: Path | None = None, rel: str = "foundation/landing_zone.yaml", strict: bool = True) -> LandingZone:
    lz = _expand(load_yaml(rel, root), root)
    if strict:
        problems = validate(lz)
        if problems:
            raise KnowledgeValidationError([f"{rel}: {p}" for p in problems])
    return lz
