"""Generated renderings for M11: semantic views (from the KPI registry), Cortex Search DDL, Cortex Agent
specs and the KPI glossary. Fails (no output) when the registry violates one definition per KPI."""

from __future__ import annotations

import yaml

from altitude.core.generated import stamp

from . import cortex, harness, kpi_registry

REG_SRC = "knowledge/semantic/kpi_registry.yaml"
TPL_SRC = "knowledge/airready/cortex_templates.yaml"


def glossary_md(registry: kpi_registry.Registry) -> str:
    lines = ["# Certified KPI glossary", "", "One definition per KPI; generated from the KPI registry.", "",
             "| KPI | Name | Domain | Definition | Synonyms | Owner |", "|---|---|---|---|---|---|"]
    for k in sorted(registry.doc["kpis"], key=lambda x: (x["domain"], x["id"])):
        if k["certified"]:
            lines.append(f"| {k['id']} | {k['name']} | {k['domain']} | `{k['expression']}` | "
                         f"{', '.join(k['synonyms'])} | {k['owner']} |")
    return "\n".join(lines) + "\n"


def generate() -> dict[str, str]:
    registry = kpi_registry.load()          # raises KPIDefinitionConflict on a second definition
    templates = cortex.load_templates()
    golden = harness.load_golden()
    cortex.check_all()
    out: dict[str, str] = {}
    for domain, ddl in kpi_registry.semantic_views(registry).items():
        out[f"airready/semantic_views/sv_{domain}.sql"] = stamp(ddl, ".sql", REG_SRC)
    for s in templates.get("search_services", []):
        out[f"airready/cortex_search/{s['name'].lower()}.sql"] = stamp(cortex.search_service_sql(s), ".sql", TPL_SRC)
    for a in templates.get("agents", []):
        body = yaml.safe_dump(cortex.agent_spec(a, templates, registry, golden), sort_keys=False, width=110, allow_unicode=True)
        out[f"airready/cortex_agents/{a['name'].lower()}.yaml"] = stamp(
            f"# Cortex Agent specification {a['database']}.{a['schema']}.{a['name']} (role {a['role']}).\n"
            "# Deploy with CREATE AGENT ... FROM SPECIFICATION after the golden-question harness passes.\n" + body,
            ".yaml", f"{TPL_SRC}, {REG_SRC}")
    out["airready/kpi_glossary.md"] = stamp(glossary_md(registry), ".md", REG_SRC)
    return out
