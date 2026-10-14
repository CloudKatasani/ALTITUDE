"""Generated ETL artifacts under ``generated/etl/`` (principle 8).

- ``dbt_macros/*.sql``: starter macros every generated dbt project can use (schema naming, deterministic
  dedupe for SET-table / lookup semantics, empty-string and case-insensitivity normalisation);
- ``component_mappings.md``: the per-tool component -> target catalogue and ETL / scheduler known issues,
  rendered from ``knowledge/etl`` and ``knowledge/schedulers``.
"""

from __future__ import annotations

from altitude.core.generated import stamp

from . import kb

_MACROS = {
    "generate_schema_name.sql": (
        "knowledge/etl/dbt_conventions.yaml",
        """{#- Use the custom schema verbatim (no target-schema prefix), as Snowflake landing zones expect. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
""",
    ),
    "dedupe.sql": (
        "knowledge/etl/known_issues.yaml#ETL-INF-02",
        """{#- Deterministic one-row-per-key selection: replaces SET-table semantics (TD-01) and
    lookup "use first/any value" policies (ETL-INF-02, ETL-SSIS-04). -#}
{% macro dedupe(relation, partition_by, order_by) %}
SELECT *
FROM {{ relation }}
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY {{ partition_by | join(', ') }}
    ORDER BY {{ order_by | join(', ') }}
) = 1
{% endmacro %}
""",
    ),
    "null_if_blank.sql": (
        "knowledge/etl/known_issues.yaml",
        """{#- Oracle treats '' as NULL (OR-01); normalise at ingestion when the programme policy says so. -#}
{% macro null_if_blank(column) -%}
NULLIF(TRIM({{ column }}), '')
{%- endmacro %}
""",
    ),
    "ci_equals.sql": (
        "knowledge/etl/known_issues.yaml",
        """{#- Case-insensitive comparison for sources with case-insensitive collation (TD-02, MS-01). -#}
{% macro ci_equals(left, right) -%}
UPPER({{ left }}) = UPPER({{ right }})
{%- endmacro %}
""",
    ),
}


def _md_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _catalogue() -> str:
    lines = ["# ETL component and scheduler catalogue", "",
             "Rendered from `knowledge/etl` and `knowledge/schedulers`; edit the YAML, then `altitude generate`.", ""]
    for tool in ("ssis", "informatica"):
        comp = kb.components(tool)
        lines += [f"## {tool}", "", "| Component | Kind | Target | Known issue |", "|---|---|---|---|"]
        for c in comp["components"]:
            lines.append(f"| {_md_cell(', '.join(c['class_ids'][:2]))} | {c['kind']} | {_md_cell(c['target'])} | "
                         f"{c.get('known_issue', '')} |")
        lines.append("")
    lines += ["## Known issues", "", "| Id | Severity | Title | Fix |", "|---|---|---|---|"]
    for ki in sorted(kb.known_issues().values(), key=lambda k: k["id"]):
        lines.append(f"| {ki['id']} | {ki['severity']} | {_md_cell(ki['title'])} | {_md_cell(ki['fix'])} |")
    lines += ["", "## Scheduler command mappings", "", "| Id | Snowflake body | Note |", "|---|---|---|"]
    for m in kb.command_mappings():
        lines.append(f"| {m['id']} | `{_md_cell(m['snowflake'])}` | {_md_cell(m['note'])} |")
    return "\n".join(lines) + "\n"


def generate() -> dict[str, str]:
    out = {f"etl/dbt_macros/{name}": stamp(body, ".sql", source) for name, (source, body) in _MACROS.items()}
    out["etl/component_mappings.md"] = stamp(_catalogue(), ".md", "knowledge/etl/*.yaml, knowledge/schedulers/*.yaml")
    return out
