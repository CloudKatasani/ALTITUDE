-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/etl/dbt_conventions.yaml. Regenerate with `altitude generate`.
{#- Use the custom schema verbatim (no target-schema prefix), as Snowflake landing zones expect. -#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
