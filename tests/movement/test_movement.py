from altitude.core.generated import is_stamped
from altitude.core.store import Store
from altitude.movement import cdc_recommendation, landing_ddl, plan_historical_load, record_load

TB = 1024 ** 4


def test_load_plan_bands_and_file_sizing():
    small = plan_historical_load([{"fq_name": "dbo.Orders", "bytes": 2 * TB, "partition_column": "OrderDate"},
                                  {"fq_name": "dbo.Region", "bytes": 1024}])
    assert small["band"] == "small" and small["tables"][0]["fq_name"] == "dbo.Orders"
    assert small["tables"][0]["files"] > 1000 and small["tables"][0]["checkpoint_unit"] == "partition"
    assert plan_historical_load([{"fq_name": "x", "bytes": 50 * TB}])["band"] == "medium"
    assert plan_historical_load([{"fq_name": "x", "bytes": 800 * TB}])["approach"].startswith("Offline transfer")


def test_landing_ddl_has_lineage_columns():
    ddl = landing_ddl("EDW.SALES.ORDERS", [("ORDER_ID", "NUMBER"), ("AMOUNT", "NUMBER(18,2)")])
    assert is_stamped(ddl) and "_ROW_HASH VARCHAR" in ddl and "LANDING.ORDERS" in ddl


def test_cdc_selection_and_known_issues():
    r = cdc_recommendation({"log_access": False})
    assert r["option"] == "batch_watermark"
    r = cdc_recommendation({"openflow_supported": True, "tables_without_pk": 3, "log_retention_hours": 24,
                            "max_outage_hours": 48})
    assert r["option"] == "openflow"
    assert {i["id"] for i in r["known_issues"]} == {"CDC-01", "CDC-03"}


def test_restartable_checkpoints():
    s = Store()
    job = record_load(s, "E1", "O1", "copy", [{"partition_key": "2026-01", "status": "loaded", "rows_loaded": 10},
                                              {"partition_key": "2026-02", "status": "failed"}])
    assert s.get("load_job", load_job_id=job)["status"] == "failed"
    record_load(s, "E1", "O1", "copy", [{"partition_key": "2026-01", "status": "failed"},  # already loaded: skipped
                                        {"partition_key": "2026-02", "status": "loaded", "rows_loaded": 12}])
    assert s.get("load_job", load_job_id=job)["status"] == "completed"
    assert s.get("load_partition", load_job_id=job, partition_key="2026-01")["rows_loaded"] == 10
