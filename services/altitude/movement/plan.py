"""Historical load planning and CDC selection."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from altitude.core.expr import ExpressionError, evaluate
from altitude.core.generated import stamp
from altitude.core.ids import stable_id
from altitude.core.knowledge import load_yaml
from altitude.core.rubric import RubricSet, default_rubrics

TB = 1024 ** 4
MB = 1024 ** 2


def _band(total_tb: float, rubrics: RubricSet) -> str:
    bands = rubrics.get("rubric.movement.volume_bands_tb")
    if total_tb < float(bands["small"]):
        return "small"
    if total_tb < float(bands["medium"]):
        return "medium"
    return "large"


def plan_historical_load(tables: list[dict], rubrics: RubricSet | None = None) -> dict:
    """``tables``: [{fq_name, bytes, partition_column?, tier?}] -> load plan with file sizing and waves."""
    rubrics = rubrics or default_rubrics()
    total_bytes = sum(int(t["bytes"]) for t in tables)
    total_tb = total_bytes / TB
    band = _band(total_tb, rubrics)
    approach = next(h["approach"] for h in load_yaml("movement/options.yaml")["historical_load"] if h["band"] == band)
    fmin, fmax = (float(rubrics.get(f"rubric.movement.file_size_mb.{k}")) for k in ("min", "max"))
    target_mb = (fmin + fmax) / 2
    throughput = float(rubrics.get("rubric.movement.load_throughput_tb_per_hour_per_xl"))
    items = []
    for t in sorted(tables, key=lambda x: (-int(x["bytes"]), x["fq_name"])):
        files = max(1, math.ceil(int(t["bytes"]) / (target_mb * MB)))
        items.append({"fq_name": t["fq_name"], "bytes": int(t["bytes"]), "files": files,
                      "partition_column": t.get("partition_column"),
                      "checkpoint_unit": "partition" if t.get("partition_column") else "file",
                      "tier": t.get("tier", "tier3")})
    return {"band": band, "total_tb": round(total_tb, 4), "approach": approach,
            "warehouse_size": rubrics.get(f"rubric.movement.warehouse_for_band.{band}"),
            "estimated_hours": round(total_tb / throughput, 2), "target_file_mb": target_mb,
            "tables": items, "rubric_version": rubrics.version,
            "rules": ["load into a landing schema with lineage columns", "never transform during historical load",
                      "checkpoint per table/partition for restartability", "suspend the load warehouse between waves"]}


def landing_ddl(table: str, columns: list[tuple[str, str]], landing_schema: str = "LANDING") -> str:
    """CREATE TABLE for the landing copy of ``table`` with the lineage columns from data."""
    lineage = load_yaml("movement/options.yaml")["lineage_columns"]
    name = table.split(".")[-1]
    cols = [f"  {c} {t}" for c, t in columns] + [f"  {c['name']} {c['type']}" for c in lineage]
    sql = f"CREATE TABLE IF NOT EXISTS {landing_schema}.{name} (\n" + ",\n".join(cols) + "\n);\n"
    return stamp(sql, ".sql", f"movement landing for {table}")


def cdc_recommendation(facts: dict, rubrics: RubricSet | None = None) -> dict:
    rubrics = rubrics or default_rubrics()
    data = load_yaml("movement/options.yaml")
    ctx = {"log_access": True, "files_land_in_object_storage": False, "openflow_supported": False,
           "prefer_native": True, "streaming_first": False, "open_source_preference": False,
           "existing_cdc_licence": False, "tables_without_pk": 0, "lob_columns": 0, "log_retention_hours": None,
           "max_outage_hours": None, "hard_deletes": False, **facts}
    choice = None
    for rule in data["cdc_rules"]:
        if evaluate(rule["when"], ctx, rubrics):
            choice = rule
            break
    issues = []
    for ki in data["cdc_known_issues"]:
        try:
            if evaluate(ki["check"], ctx, rubrics):
                issues.append({"id": ki["id"], "title": ki["title"]})
        except (ExpressionError, TypeError):
            continue
    return {"option": choice["option"], "rationale": choice["rationale"], "known_issues": issues}


def record_load(store: Any, engagement_id: str, object_id: str, method: str, partitions: list[dict]) -> str:
    """Record a load job and its partition checkpoints (restartable: already-loaded partitions are skipped)."""
    job_id = stable_id("LOAD", engagement_id, object_id, method)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if not store.get("load_job", load_job_id=job_id):
        store.insert("load_job", {"load_job_id": job_id, "engagement_id": engagement_id, "object_id": object_id,
                                  "method": method, "status": "running", "started_at": now})
    done = {r["partition_key"] for r in store.query(
        "SELECT partition_key FROM load_partition WHERE load_job_id = ? AND status = 'loaded'", [job_id])}
    for p in partitions:
        if p["partition_key"] in done:
            continue
        existing = store.get("load_partition", load_job_id=job_id, partition_key=p["partition_key"])
        row = {"rows_loaded": p.get("rows_loaded"), "checkpoint": p.get("checkpoint"), "status": p["status"]}
        if existing:
            store.update("load_partition", {"load_job_id": job_id, "partition_key": p["partition_key"]}, row)
        else:
            store.insert("load_partition", {"load_job_id": job_id, "partition_key": p["partition_key"], **row})
    states = {r["status"] for r in store.query("SELECT status FROM load_partition WHERE load_job_id = ?", [job_id])}
    status = "completed" if states == {"loaded"} else ("failed" if "failed" in states else "running")
    store.update("load_job", {"load_job_id": job_id}, {"status": status,
                                                       "completed_at": now if status == "completed" else None})
    return job_id
