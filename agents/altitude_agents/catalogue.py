"""Loaders for the agent catalogue, action catalogue and tenant policies (all knowledge-as-data)."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from altitude.core.knowledge import load_yaml

LEVELS = ("L0", "L1", "L2", "L3")


def level_rank(level: str) -> int:
    if level not in LEVELS:
        raise ValueError(f"unknown autonomy level {level!r}")
    return LEVELS.index(level)


def min_level(*levels: str) -> str:
    return min(levels, key=level_rank)


# --------------------------------------------------------------------------- agents
@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    number: int
    implemented: bool
    version: str | None
    prompt_template: str | None
    trigger: dict
    purpose: str
    max_autonomy: str
    autonomy_by_action: dict
    guardrails: tuple[str, ...]
    forbidden_statements: tuple[str, ...]
    kpi: str
    tool_scope: tuple[str, ...]
    action_types: tuple[str, ...]
    service_user: str
    service_role: str
    warehouse: str

    def action_autonomy(self, action_type: str) -> str:
        return min_level(self.autonomy_by_action.get(action_type, self.max_autonomy), self.max_autonomy)


def load_agent_catalogue(root: Path | None = None) -> dict[str, AgentSpec]:
    doc = load_yaml("agents/catalogue.yaml", root)
    out: dict[str, AgentSpec] = {}
    for a in doc["agents"]:
        ident = a["service_identity"]
        out[a["id"]] = AgentSpec(
            agent_id=a["id"], name=a["name"], number=a["number"], implemented=a["implemented"],
            version=a.get("version"), prompt_template=a.get("prompt_template"), trigger=a["trigger"],
            purpose=a["purpose"], max_autonomy=a["max_autonomy"], autonomy_by_action=a.get("autonomy_by_action", {}),
            guardrails=tuple(a["guardrails"]), forbidden_statements=tuple(a.get("forbidden_statements", [])),
            kpi=a["kpi"], tool_scope=tuple(a["tool_scope"]), action_types=tuple(a["action_types"]),
            service_user=ident["user"], service_role=ident["role"], warehouse=ident["warehouse"])
    return out


# --------------------------------------------------------------------------- actions
@dataclass(frozen=True)
class ActionType:
    action_type: str
    object_type: str
    params: dict
    sql_template: str | None
    rollback_template: str | None
    capture: tuple[str, ...]
    reversible: bool
    executable: bool
    idempotent_required: bool
    description: str = ""


@dataclass(frozen=True)
class PreApproved:
    entry_id: str
    tenants: tuple[str, ...]
    action_type: str
    agents: tuple[str, ...]
    max_autonomy: str
    include: tuple[str, ...]
    exclude: tuple[str, ...]
    requires_idempotent_flag: bool
    blast_radius: dict
    change_window: dict
    guard: dict | None
    rollback: str

    def applies_to_tenant(self, tenant_id: str) -> bool:
        return "*" in self.tenants or tenant_id in self.tenants

    def in_scope(self, target: str) -> bool:
        t = target.upper()
        return (any(fnmatch.fnmatchcase(t, p.upper()) for p in self.include)
                and not any(fnmatch.fnmatchcase(t, p.upper()) for p in self.exclude))


@dataclass
class ActionCatalogue:
    types: dict[str, ActionType]
    pre_approved: list[PreApproved] = field(default_factory=list)

    @classmethod
    def load(cls, root: Path | None = None) -> "ActionCatalogue":
        return cls.from_doc(load_yaml("agents/action_catalogue.yaml", root))

    @classmethod
    def from_doc(cls, doc: dict) -> "ActionCatalogue":
        types = {}
        for t in doc["action_types"]:
            types[t["action_type"]] = ActionType(
                action_type=t["action_type"], object_type=t["object_type"], params=dict(t["params"]),
                sql_template=t.get("sql_template"), rollback_template=t.get("rollback_template"),
                capture=tuple(t["capture"]), reversible=t["reversible"], executable=t["executable"],
                idempotent_required=t.get("idempotent_required", False), description=t.get("description", ""))
        pre = []
        for p in doc["pre_approved"]:
            pre.append(PreApproved(
                entry_id=p["id"], tenants=tuple(p["tenants"]), action_type=p["action_type"], agents=tuple(p["agents"]),
                max_autonomy=p["max_autonomy"], include=tuple(p["scope"]["include"]),
                exclude=tuple(p["scope"].get("exclude", [])),
                requires_idempotent_flag=p.get("requires_idempotent_flag", False), blast_radius=p["blast_radius"],
                change_window=p["change_window"], guard=p.get("guard"), rollback=p["rollback"]))
        return cls(types, pre)

    def entries_for(self, tenant_id: str, action_type: str, agent_id: str) -> list[PreApproved]:
        return [p for p in self.pre_approved
                if p.action_type == action_type and p.applies_to_tenant(tenant_id) and agent_id in p.agents]


# --------------------------------------------------------------------------- tenant policy
@dataclass(frozen=True)
class TenantPolicy:
    tenant_id: str
    autonomy_caps: dict
    break_glass_users: tuple[str, ...]
    idempotent_tasks: tuple[str, ...]
    approvers: dict
    mfa_authentication_policy: str
    quarantine_tag: str
    system_roles: tuple[str, ...]

    def cap(self, agent_id: str) -> str:
        return self.autonomy_caps.get(agent_id, "L1")

    @classmethod
    def from_entry(cls, t: dict) -> "TenantPolicy":
        return cls(tenant_id=t["tenant_id"], autonomy_caps=dict(t["autonomy_caps"]),
                   break_glass_users=tuple(t["break_glass_users"]), idempotent_tasks=tuple(t["idempotent_tasks"]),
                   approvers={k: tuple(v) for k, v in t["approvers"].items()},
                   mfa_authentication_policy=t["mfa_authentication_policy"], quarantine_tag=t["quarantine_tag"],
                   system_roles=tuple(t["system_roles"]))


def load_tenant_policy(tenant_id: str, root: Path | None = None, overrides: dict[str, Any] | None = None) -> TenantPolicy:
    doc = load_yaml("agents/tenant_policies.yaml", root)
    entries = {t["tenant_id"]: t for t in doc["tenants"]}
    entry = dict(entries.get(tenant_id) or entries["default"])
    entry["tenant_id"] = tenant_id
    entry.update(overrides or {})
    return TenantPolicy.from_entry(entry)


def load_error_signatures(root: Path | None = None) -> list[dict]:
    return list(load_yaml("agents/error_signatures.yaml", root)["signatures"])


def load_behaviour_changes(root: Path | None = None) -> list[dict]:
    return list(load_yaml("agents/behaviour_changes.yaml", root)["entries"])
