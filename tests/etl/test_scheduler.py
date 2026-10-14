"""M9 acceptance: scheduler definitions produce a valid task graph (acyclic, all predecessors defined) and
an Airflow DAG file that is valid Python."""

import ast

import pytest

from altitude.etl.controlm import parse_controlm
from altitude.etl.scheduler import (SchedJob, SchedulerDAG, airflow_edges, convert, parse_task_sql, plan,
                                    validate_airflow, validate_task_sql)
from altitude.etl.sqlagent import parse_sqlagent

from .conftest import CONTROLM, SQLAGENT


@pytest.fixture(params=["controlm", "sqlagent"])
def conversion(request):
    dag = parse_controlm(CONTROLM)[0] if request.param == "controlm" else parse_sqlagent(SQLAGENT)
    return convert(dag)


def test_task_graph_is_valid(conversion):
    assert validate_task_sql(conversion.task_sql) == []
    tasks = parse_task_sql(conversion.task_sql)
    assert set(tasks) == {f"OPS.ORCHESTRATION.{j}" for j in conversion.dag.jobs}
    for name, t in tasks.items():
        assert all(p in tasks for p in t["after"])
    roots = [n for n, t in tasks.items() if not t["after"] and not t["finalize"]]
    assert len(roots) == len(conversion.graphs)
    assert all(tasks[f"OPS.ORCHESTRATION.{g.root}"]["schedule"] for g in conversion.graphs)


def test_airflow_dags_are_valid_python_with_the_same_dependencies(conversion):
    for g in conversion.graphs:
        src = next(s for f, s in conversion.airflow.items() if f.endswith(f"__{g.root}.py"))
        compile(src, "dag.py", "exec")
        ast.parse(src)
        assert validate_airflow(src) == []
        expected = {(p, j) for j in g.members for p in conversion.dag.jobs[j].predecessors}
        if g.finalizer:
            fin = conversion.dag.jobs[g.finalizer]
            expected |= {(p, g.finalizer) for p in fin.failure_sources}
        assert airflow_edges(src) == expected


def test_controlm_semantics():
    conv = convert(parse_controlm(CONTROLM)[0])
    jobs = conv.dag.jobs
    assert jobs["dwh_build_aggregates"].predecessors == ["dwh_load_dim_customer", "dwh_load_sales_mart"]
    assert jobs["dwh_extract_erp"].schedule == "30 1 * * 1-5" and jobs["dwh_archive_logs"].schedule == "0 23 * * 0"
    assert jobs["dwh_extract_erp"].external_conditions == ["ERP-FILES-READY"]
    assert (jobs["dwh_load_dim_customer"].retries, jobs["dwh_load_dim_customer"].retry_delay_minutes) == (1, 10)
    assert jobs["dwh_load_dim_customer"].sla_minutes == 45 and jobs["dwh_build_aggregates"].sla_time == "06:00"
    assert {i.id for i in conv.dag.issues} >= {"SCH-01", "SCH-02", "SCH-03", "SCH-04", "SCH-07"}
    sql = conv.task_sql
    assert "EXECUTE DBT PROJECT OPS.ORCHESTRATION.DWH_DBT ARGS = 'build --select tag:wf_sales_dw'" in sql
    assert "tag:load_sales_mart" in sql and "TASK_AUTO_RETRY_ATTEMPTS = 3" in sql
    assert "CREATE OR REPLACE ALERT OPS.ORCHESTRATION.sla_dwh_build_aggregates" in sql
    assert "USING CRON 0 6 * * 1-5 UTC" in sql
    src = next(iter(v for k, v in conv.airflow.items() if "extract_erp" in k))
    assert "sla=timedelta(minutes=45)" in src and "retries=3" in src


def test_sqlagent_semantics():
    conv = convert(parse_sqlagent(SQLAGENT))
    jobs = conv.dag.jobs
    assert "dwh_nightly_load_start_finance_export" not in jobs          # sp_start_job step became an edge
    assert jobs["fin_export_extract_extract_gl"].predecessors == ["dwh_nightly_load_reset_export_queue"]
    assert jobs["dwh_nightly_load_purge_staging"].schedule == "15 2 * * 1-5"
    fin = jobs["dwh_nightly_load_notify_failure"]
    assert fin.trigger == "one_failed" and set(fin.failure_sources) == {
        "dwh_nightly_load_purge_staging", "dwh_nightly_load_load_sales_mart"}
    (g,) = conv.graphs
    assert g.finalizer == "dwh_nightly_load_notify_failure"
    assert "FINALIZE = OPS.ORCHESTRATION.dwh_nightly_load_purge_staging" in conv.task_sql
    assert "CALL dbo.usp_purge_stage();" in conv.task_sql
    assert "CALL SYSTEM$SEND_EMAIL('OPS_EMAIL_INT', 'dwh-oncall@example.com'" in conv.task_sql
    assert {i.id for i in conv.dag.issues} >= {"SCH-03", "SCH-05", "SCH-06", "SCH-07"}
    assert 'trigger_rule="one_failed"' in next(iter(conv.airflow.values()))


def test_multiple_roots_get_a_synthetic_root():
    dag = SchedulerDAG("controlm", "F", "f.xml", {
        "a": SchedJob("a", "A", "dbt run", schedule="0 2 * * *"),
        "b": SchedJob("b", "B", "dbt run", schedule="30 1 * * *"),
        "c": SchedJob("c", "C", "dbt run", predecessors=["a", "b"]),
    })
    conv = convert(dag)
    (g,) = conv.graphs
    assert g.synthetic_root and g.schedule == "30 1 * * *"
    assert validate_task_sql(conv.task_sql) == [] and validate_airflow(next(iter(conv.airflow.values()))) == []
    assert any(i.id == "SCH-08" for i in dag.issues)


def test_validators_reject_broken_graphs():
    bad = SchedulerDAG("controlm", "F", "f.xml", {
        "a": SchedJob("a", "A", predecessors=["c"]), "b": SchedJob("b", "B", predecessors=["a"]),
        "c": SchedJob("c", "C", predecessors=["b"]), "d": SchedJob("d", "D", predecessors=["zz"])})
    problems = bad.validate()
    assert any("zz" in p for p in problems) and any("cycle" in p for p in problems)
    with pytest.raises(ValueError):
        plan(bad)
    sql = ("CREATE OR REPLACE TASK x.a\n  WAREHOUSE = W\n  AFTER x.b\nAS\n  SELECT 1;\n"
           "CREATE OR REPLACE TASK x.b\n  WAREHOUSE = W\n  AFTER x.a\nAS\n  SELECT 1;\n"
           "CREATE OR REPLACE TASK x.c\n  WAREHOUSE = W\n  AFTER x.missing\nAS\n  SELECT 1;\n")
    problems = validate_task_sql(sql)
    assert any("x.missing" in p for p in problems) and any("cycle" in p for p in problems)
    assert validate_airflow("def broken(:\n") and validate_airflow("a = 1\nb >> a\n")
