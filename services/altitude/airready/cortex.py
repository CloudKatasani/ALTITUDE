"""Cortex Search service DDL and Cortex Agent specification templates (Section 15.2 AI pack)."""

from __future__ import annotations

from pathlib import Path

from altitude.core.errors import KnowledgeValidationError
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics

from .kpi_registry import Registry, snake

TEMPLATES = "airready/cortex_templates.yaml"
_LAG_HOURS = {"minute": 1 / 60, "minutes": 1 / 60, "hour": 1.0, "hours": 1.0, "day": 24.0, "days": 24.0}


def load_templates(root: Path | None = None) -> dict:
    return load_yaml(TEMPLATES, root)


def lag_hours(target_lag: str) -> float:
    n, unit = target_lag.split()
    return float(n) * _LAG_HOURS[unit]


def validate(templates: dict, registry: Registry, golden: dict, rubrics: RubricSet | None = None) -> list[str]:
    rubrics = rubrics or default_rubrics()
    problems = []
    services = {s["id"]: s for s in templates.get("search_services", [])}
    max_lag = float(rubrics.get("rubric.airready.rag_target_lag_max_hours"))
    for s in services.values():
        if s["acl_attribute"] not in s["attributes"]:
            problems.append(f"{TEMPLATES}: {s['id']}: ACL attribute {s['acl_attribute']} must be a filterable attribute")
        if lag_hours(s["target_lag"]) > max_lag:
            problems.append(f"{TEMPLATES}: {s['id']}: target lag {s['target_lag']} exceeds "
                            f"rubric.airready.rag_target_lag_max_hours ({max_lag})")
    questions = {q["id"] for q in golden["questions"]}
    for a in templates.get("agents", []):
        for d in a["semantic_domains"]:
            if d not in registry.domains:
                problems.append(f"{TEMPLATES}: {a['id']}: unknown KPI domain {d!r}")
        for s in a["search_services"]:
            if s not in services:
                problems.append(f"{TEMPLATES}: {a['id']}: unknown search service {s}")
        for q in a["sample_questions"]:
            if q not in questions:
                problems.append(f"{TEMPLATES}: {a['id']}: unknown golden question {q}")
    return problems


def search_service_sql(s: dict) -> str:
    cols = [s["search_column"], *s["attributes"]]
    return (f"CREATE OR REPLACE CORTEX SEARCH SERVICE {s['database']}.{s['schema']}.{s['name']}\n"
            f"  ON {s['search_column']}\n"
            f"  ATTRIBUTES {', '.join(s['attributes'])}\n"
            f"  WAREHOUSE = {s['warehouse']}\n"
            f"  TARGET_LAG = '{s['target_lag']}'\n"
            f"  EMBEDDING_MODEL = '{s['embedding_model']}'\n"
            f"  COMMENT = '{s['description'].replace(chr(39), chr(39) * 2)}'\n"
            f"  AS (\n    SELECT {', '.join(cols)}\n    FROM {s['source_table']}\n  );\n")


def agent_spec(agent: dict, templates: dict, registry: Registry, golden: dict) -> dict:
    services = {s["id"]: s for s in templates.get("search_services", [])}
    questions = {q["id"]: q["question"] for q in golden["questions"]}
    tools, resources = [], {}
    for d in agent["semantic_domains"]:
        dom = registry.domains[d]
        name = f"analyst_{d}"
        kpis = [k["name"] for k in registry.doc["kpis"] if k["domain"] == d and k["certified"]]
        tools.append({"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": name,
                                    "description": f"{dom['description']} Certified KPIs: {', '.join(kpis)}."}})
        resources[name] = {"semantic_view": dom["semantic_view"],
                           "execution_environment": {"type": "warehouse", "warehouse": agent["warehouse"]}}
    for sid in agent["search_services"]:
        s = services[sid]
        name = f"search_{snake(s['name'])}"
        tools.append({"tool_spec": {"type": "cortex_search", "name": name, "description": s["description"]}})
        resources[name] = {"name": f"{s['database']}.{s['schema']}.{s['name']}", "max_results": 5,
                           "id_column": s["attributes"][0], "title_column": s["attributes"][0],
                           "filter": {"@eq": {s["acl_attribute"]: "{{ user.acl_group }}"}}}
    return {
        "models": {"orchestration": "auto"},
        "instructions": {"orchestration": agent["instructions"].strip(),
                         "response": "Cite the certified KPI (id) or document used; say when the sources do not answer.",
                         "sample_questions": [{"question": questions[q]} for q in agent["sample_questions"]]},
        "tools": tools,
        "tool_resources": resources,
    }


def check_all(root: Path | None = None) -> None:
    from . import harness, kpi_registry

    problems = validate(load_templates(root), kpi_registry.load(root), harness.load_golden(root))
    if problems:
        raise KnowledgeValidationError(problems)
