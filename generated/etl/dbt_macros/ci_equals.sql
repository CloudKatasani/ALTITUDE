-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/etl/known_issues.yaml. Regenerate with `altitude generate`.
{#- Case-insensitive comparison for sources with case-insensitive collation (TD-02, MS-01). -#}
{% macro ci_equals(left, right) -%}
UPPER({{ left }}) = UPPER({{ right }})
{%- endmacro %}
