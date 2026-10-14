"""M9 ETL & scheduler converters.

- ``ssis`` / ``informatica``  export parsers -> common mapping graph (``graph``)
- ``expr``                    SSIS / Informatica expression languages -> Snowflake SQL
- ``classify``                passthrough / transform / complex; retire / lift / re-engineer
- ``sqlgen`` / ``dbt``        mapping graph -> stg_/int_/dim_/fct_/agg_ dbt project with tests and docs
- ``harness`` / ``synthetic`` dbt compile + run + test in DuckDB on synthetic source data
- ``controlm`` / ``sqlagent`` scheduler exports -> dependency DAG (``scheduler``) -> task graph SQL + Airflow
"""
