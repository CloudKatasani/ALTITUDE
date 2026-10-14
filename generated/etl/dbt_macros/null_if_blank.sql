-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/etl/known_issues.yaml. Regenerate with `altitude generate`.
{#- Oracle treats '' as NULL (OR-01); normalise at ingestion when the programme policy says so. -#}
{% macro null_if_blank(column) -%}
NULLIF(TRIM({{ column }}), '')
{%- endmacro %}
