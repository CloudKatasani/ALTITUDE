"""Generated renderings of the agent fleet (principle 8): Cortex Agent specs, service identities and the
fleet catalogue. Output under ``generated/agents/``; regenerate with ``altitude generate``."""

from __future__ import annotations

import inspect
import typing

import yaml

from altitude.core.generated import stamp

from .catalogue import ActionCatalogue, load_agent_catalogue
from .tools import TOOLS

SRC_CAT = "knowledge/agents/catalogue.yaml"
SRC_ACT = "knowledge/agents/action_catalogue.yaml"
TOOL_DB = "ALTITUDE_AGENTS"
OBS_DB = "OBS"

# SNOWFLAKE database role that exposes each ACCOUNT_USAGE view the tools read (least privilege).
DB_ROLE_FOR_TABLE = {
    "METERING_DAILY_HISTORY": "USAGE_VIEWER", "WAREHOUSE_METERING_HISTORY": "USAGE_VIEWER",
    "WAREHOUSE_LOAD_HISTORY": "USAGE_VIEWER", "QUERY_ATTRIBUTION_HISTORY": "USAGE_VIEWER",
    "QUERY_HISTORY": "GOVERNANCE_VIEWER", "ACCESS_HISTORY": "GOVERNANCE_VIEWER",
    "TAG_REFERENCES": "GOVERNANCE_VIEWER", "OBJECT_DEPENDENCIES": "GOVERNANCE_VIEWER",
    "TASK_HISTORY": "USAGE_VIEWER", "COPY_HISTORY": "USAGE_VIEWER",
    "USERS": "SECURITY_VIEWER", "ROLES": "SECURITY_VIEWER", "GRANTS_TO_USERS": "SECURITY_VIEWER",
    "GRANTS_TO_ROLES": "SECURITY_VIEWER", "LOGIN_HISTORY": "SECURITY_VIEWER",
    "VIEWS": "OBJECT_VIEWER", "TABLES": "OBJECT_VIEWER", "COLUMNS": "OBJECT_VIEWER",
}
# Write privileges an L3-capable action type needs on its (pre-approved) targets.
WRITE_PRIVILEGE = {"warehouse.set_auto_suspend": ("MODIFY", "WAREHOUSE"), "task.rerun": ("OPERATE", "TASK")}

_JSON_TYPES = {int: "integer", float: "number", str: "string", bool: "boolean"}


def _input_schema(fn) -> dict:
    hints = typing.get_type_hints(fn)
    props, required = {}, []
    for name, p in list(inspect.signature(fn).parameters.items())[1:]:
        hint = hints.get(name, str)
        args = [a for a in typing.get_args(hint) if a is not type(None)] or [hint]
        base = typing.get_origin(args[0]) or args[0]
        if base is list:
            props[name] = {"type": "array", "items": {"type": "string"}}
        else:
            props[name] = {"type": _JSON_TYPES.get(base, "string")}
        if p.default is inspect.Parameter.empty:
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _slug(agent_id: str) -> str:
    return agent_id.removeprefix("AG-").lower().replace("-", "_")


def cortex_spec(agent, pre_approved: list) -> dict:
    l3 = sorted({p.action_type for p in pre_approved if agent.agent_id in p.agents and p.max_autonomy == "L3"})
    instructions = (
        f"You are the {agent.name} ({agent.agent_id}). {agent.purpose} "
        f"Maximum autonomy: {agent.max_autonomy}. Guardrails: {', '.join(agent.guardrails) or 'read-only'}. "
        "Use only the provided read-only tools; cite evidence IDs for every claim; state confidence and rationale. "
        "Never execute a change yourself: draft it for the ALTITUDE action gateway, which enforces approvals "
        f"(L2) and the pre-approved catalogue (L3: {', '.join(l3) or 'none'}).")
    return {
        "models": {"orchestration": "auto"},
        "instructions": {"orchestration": instructions,
                         "response": "Lead with the decision, then evidence IDs, confidence and the drafted action."},
        "tools": [{"tool_spec": {"type": "generic", "name": t, "description": TOOLS[t].description,
                                 "input_schema": _input_schema(TOOLS[t].fn)}}
                  for t in agent.tool_scope if t in TOOLS],
        "tool_resources": {t: {"type": "procedure", "identifier": f"{TOOL_DB}.TOOLS.{t.upper()}",
                               "execution_environment": {"type": "warehouse", "warehouse": agent.warehouse}}
                           for t in agent.tool_scope if t in TOOLS},
    }


def identities_sql(agents: dict, catalogue: ActionCatalogue) -> str:
    out = ["-- One service user + role per agent (Section 18.3): distinct machine identities, minimal tool scope.",
           "-- Read access comes from SNOWFLAKE database roles / the Package O OBS database; writes only for",
           "-- action types in the pre-approved (L3) catalogue, granted per target by the tenant's IaC.", ""]
    for a in sorted(agents.values(), key=lambda x: x.number):
        out.append(f"-- {a.number}. {a.name} ({a.agent_id}) max autonomy {a.max_autonomy}"
                   + ("" if a.implemented else " [catalogue only; not yet implemented]"))
        out.append(f"CREATE ROLE IF NOT EXISTS {a.service_role} COMMENT = 'ALTITUDE agent role: {a.name}';")
        out.append(f"CREATE USER IF NOT EXISTS {a.service_user} TYPE = SERVICE DEFAULT_ROLE = {a.service_role} "
                   f"DEFAULT_WAREHOUSE = {a.warehouse} COMMENT = 'ALTITUDE agent identity: {a.name}';")
        out.append(f"GRANT ROLE {a.service_role} TO USER {a.service_user};")
        out.append(f"GRANT USAGE ON WAREHOUSE {a.warehouse} TO ROLE {a.service_role};")
        tables = sorted({tb for t in a.tool_scope if t in TOOLS for tb in TOOLS[t].tables})
        for role in sorted({DB_ROLE_FOR_TABLE[t] for t in tables if t in DB_ROLE_FOR_TABLE}):
            out.append(f"GRANT DATABASE ROLE SNOWFLAKE.{role} TO ROLE {a.service_role};")
        out.append(f"GRANT USAGE ON DATABASE {OBS_DB} TO ROLE {a.service_role};")
        out.append(f"GRANT USAGE ON SCHEMA {OBS_DB}.CURATED TO ROLE {a.service_role};")
        for t in tables:
            out.append(f"GRANT SELECT ON VIEW {OBS_DB}.CURATED.{t} TO ROLE {a.service_role};")
        for t in a.tool_scope:
            if t in TOOLS:
                out.append(f"GRANT USAGE ON PROCEDURE {TOOL_DB}.TOOLS.{t.upper()}(VARIANT) TO ROLE {a.service_role};")
        for p in catalogue.pre_approved:
            if a.agent_id in p.agents and p.max_autonomy == "L3" and p.action_type in WRITE_PRIVILEGE:
                priv, kind = WRITE_PRIVILEGE[p.action_type]
                out.append(f"-- L3 {p.entry_id}: GRANT {priv} ON {kind} <target> TO ROLE {a.service_role} for each "
                           f"target matching {list(p.include)} excluding {list(p.exclude)}")
        out.append("")
    return "\n".join(out)


def catalogue_md(agents: dict, catalogue: ActionCatalogue) -> str:
    lines = ["# Agent fleet catalogue", "",
             "| # | Agent | Trigger | Max autonomy | Guardrails | KPI | Tools | Identity | Status |",
             "|---|---|---|---|---|---|---|---|---|"]
    for a in sorted(agents.values(), key=lambda x: x.number):
        lines.append(f"| {a.number} | {a.name} | {a.trigger['description']} | {a.max_autonomy} | "
                     f"{', '.join(a.guardrails) or '—'} | {a.kpi} | {', '.join(a.tool_scope)} | "
                     f"{a.service_user} / {a.service_role} | {'v1 ' + str(a.version) if a.implemented else 'planned'} |")
    lines += ["", "## Pre-approved action catalogue (L3)", "",
              "| Entry | Tenants | Action | Agents | Scope | Rollback | Guard |", "|---|---|---|---|---|---|---|"]
    for p in catalogue.pre_approved:
        guard = p.guard["metric"] if p.guard else "—"
        lines.append(f"| {p.entry_id} | {', '.join(p.tenants)} | {p.action_type} | {', '.join(p.agents)} | "
                     f"{', '.join(p.include)} excl. {', '.join(p.exclude) or '—'} | {p.rollback} | {guard} |")
    lines += ["", "## Action types", "", "| Action | Object | SQL | Rollback | Executable |", "|---|---|---|---|---|"]
    for t in catalogue.types.values():
        lines.append(f"| {t.action_type} | {t.object_type} | `{t.sql_template or '(draft only)'}` | "
                     f"`{t.rollback_template or '—'}` | {'yes' if t.executable else 'no (PR)'} |")
    return "\n".join(lines) + "\n"


def generate() -> dict[str, str]:
    agents = load_agent_catalogue()
    cat = ActionCatalogue.load()
    out = {}
    for a in agents.values():
        if a.implemented:
            body = yaml.safe_dump(cortex_spec(a, cat.pre_approved), sort_keys=False, width=110)
            out[f"agents/cortex/{_slug(a.agent_id)}.yaml"] = stamp(
                f"# Cortex Agent specification for {a.name} — deploy with CREATE AGENT ... FROM SPECIFICATION.\n"
                + body, ".yaml", SRC_CAT)
    out["agents/sql/service_identities.sql"] = stamp(identities_sql(agents, cat), ".sql", SRC_CAT)
    out["agents/catalogue.md"] = stamp(catalogue_md(agents, cat), ".md", f"{SRC_CAT}, {SRC_ACT}")
    return out
