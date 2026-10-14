-- AUTO-GENERATED — DO NOT EDIT. Source: knowledge/etl/known_issues.yaml#ETL-INF-02. Regenerate with `altitude generate`.
{#- Deterministic one-row-per-key selection: replaces SET-table semantics (TD-01) and
    lookup "use first/any value" policies (ETL-INF-02, ETL-SSIS-04). -#}
{% macro dedupe(relation, partition_by, order_by) %}
SELECT *
FROM {{ relation }}
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY {{ partition_by | join(', ') }}
    ORDER BY {{ order_by | join(', ') }}
) = 1
{% endmacro %}
