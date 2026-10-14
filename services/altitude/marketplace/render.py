"""Snowflake renderings for the marketplace.

Products: a secure-view schema per product exposing exactly the contract columns, a share, and an
organization (internal marketplace) listing whose manifest carries owner, SLA, classification and data
dictionary. Agents: a Cortex Agent specification over the agent's semantic view or search service.
Listing and agent syntax follow current Snowflake documentation at the time of writing; re-verify per
engagement (the spec's rule for every Snowflake surface).
"""

from __future__ import annotations

import json

import yaml

from altitude.core.theme import token


def _ident(product_id: str) -> str:
    return product_id.replace("-", "_")


def listing_manifest(p: dict) -> str:
    doc = {
        "title": p["name"],
        "subtitle": f"{p['domain'].title()} data product · {p['classification']}",
        "description": p["description"] + (f"\n\nCertified KPIs: {', '.join(p['kpis'])}." if p.get("kpis") else ""),
        "organization_profile": "INTERNAL",
        "organization_targets": {"discovery": [{"all_internal_accounts": True}],
                                 "access": [{"all_internal_accounts": True}]},
        "support_contact": p["steward"],
        "approver_contact": p["owner"],
        "data_dictionary": {"featured": {"database_objects": [
            {"name": o["table"].split(".")[-1], "schema": _ident(p["id"]), "domain": "VIEW"} for o in p["objects"]]}},
    }
    if p.get("freshness"):
        doc["data_attributes"] = {"refresh_rate": f"Daily by {p['freshness']['deadline_utc']} UTC"}
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)


def product_sql(p: dict, database: str = "MARKETPLACE") -> str:
    sch = f"{database}.{_ident(p['id'])}"
    share = f"{_ident(p['id'])}_SHARE"
    out = [f"-- Data product {p['id']} ({p['name']}): owner {p['owner']}, classification {p['classification']}",
           f"CREATE DATABASE IF NOT EXISTS {database};", f"CREATE SCHEMA IF NOT EXISTS {sch} WITH MANAGED ACCESS;"]
    for o in p["objects"]:
        view = o["table"].split(".")[-1]
        out.append(f"CREATE OR REPLACE SECURE VIEW {sch}.{view} COMMENT = '{p['name']} — contract view' AS "
                   f"SELECT {', '.join(o['columns'])} FROM {o['table']};")
    out += [f"CREATE SHARE IF NOT EXISTS {share};",
            f"GRANT USAGE ON DATABASE {database} TO SHARE {share};",
            f"GRANT USAGE ON SCHEMA {sch} TO SHARE {share};"]
    out += [f"GRANT SELECT ON VIEW {sch}.{o['table'].split('.')[-1]} TO SHARE {share};" for o in p["objects"]]
    out.append(f"CREATE ORGANIZATION LISTING IF NOT EXISTS {_ident(p['id'])} SHARE {share} AS\n$$\n"
               f"{listing_manifest(p)}$$;")
    return "\n".join(out) + "\n"


def agent_spec(a: dict, products_by_id: dict[str, dict]) -> dict:
    if a["kind"] == "cortex_search":
        tool = {"tool_spec": {"type": "cortex_search", "name": "search"}}
        resources = {"search": {"name": a["search_service"], "max_results": 5}}
    else:
        tool = {"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "analyst"}}
        resources = {"analyst": {"semantic_view": a["semantic_view"]}}
    sources = [products_by_id[d]["name"] for d in a["products"] if d in products_by_id]
    return {
        "name": _ident(a["id"]),
        "comment": a["description"],
        "profile": {"display_name": a["name"]},
        "instructions": {
            "response": (f"You are {a['name']}, published by {token('COMPANY_NAME')}. Answer only from the tools; "
                         "cite the certified KPI or document you used; if the data cannot answer, say so."),
            "orchestration": "Use the tool for every factual answer. Never reveal masked values.",
            "sample_questions": [{"question": q} for q in a["sample_questions"]],
        },
        "tools": [tool],
        "tool_resources": resources,
        "x_altitude": {"run_as_role": a["role"], "audience": a["audience"], "data_products": sources,
                       "evaluation_golden_questions": a["golden_questions"]},
    }


def agent_sql(a: dict, products_by_id: dict[str, dict], database: str = "MARKETPLACE") -> str:
    spec = agent_spec(a, products_by_id)
    return (f"-- Marketplace agent {a['id']} ({a['name']}), runs as {a['role']}\n"
            f"CREATE SCHEMA IF NOT EXISTS {database}.AGENTS;\n"
            f"CREATE OR REPLACE AGENT {database}.AGENTS.{spec['name']}\n"
            f"  COMMENT = '{a['description'].replace(chr(39), chr(39) * 2)}'\n"
            f"  FROM SPECIFICATION\n$$\n{yaml.safe_dump({k: v for k, v in spec.items() if k not in ('name', 'comment', 'x_altitude')}, sort_keys=False)}$$;\n"
            f"GRANT USAGE ON AGENT {database}.AGENTS.{spec['name']} TO ROLE {a['role']};\n")


def catalogue_markdown(products: list[dict], agents: list[dict]) -> str:
    lines = ["# Marketplace catalogue", "", "## Data products", "",
             "| ID | Name | Domain | Owner | Classification | Endpoints |", "|---|---|---|---|---|---|"]
    lines += [f"| {p['id']} | {p['name']} | {p['domain']} | {p['owner']} | {p['classification']} | "
              f"{', '.join(p['endpoints'])} |" for p in products]
    lines += ["", "## Agents", "", "| ID | Name | Kind | Data products | Role | Golden questions |", "|---|---|---|---|---|---|"]
    lines += [f"| {a['id']} | {a['name']} | {a['kind']} | {', '.join(a['products']) or '—'} | {a['role']} | "
              f"{a['golden_questions']} |" for a in agents]
    return "\n".join(lines) + "\n"


def to_json(obj: dict) -> str:
    return json.dumps(obj, indent=2, sort_keys=True)
