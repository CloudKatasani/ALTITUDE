import json

import duckdb
import yaml

from altitude.cli import main
from altitude.core.store import Store
from altitude.validation.synthetic import CUSTOMER


def test_cli_run_accept_summary(tmp_path, capsys):
    src, tgt = tmp_path / "src.duckdb", tmp_path / "tgt.duckdb"
    with duckdb.connect(str(src)) as c:
        c.execute(CUSTOMER)
    with duckdb.connect(str(tgt)) as c:
        c.execute(CUSTOMER + "UPDATE customer SET middle_name = '' WHERE middle_name IS NULL;")
    cfg = tmp_path / "tables.yaml"
    cfg.write_text(yaml.safe_dump({"tables": [{
        "object_id": "CRM.CUSTOMER", "source_table": "customer", "tier": "tier1", "key_columns": ["customer_id"],
        "source_dialect": "oracle", "engagement_id": "ENG-1", "data_owner": "jane@client"}]}))
    db = tmp_path / "cp.duckdb"
    args = ["validation", "run", "--config", str(cfg), "--source", str(src), "--target", str(tgt), "--db", str(db),
            "--mismatch-dir", str(tmp_path / "mm"), "--as-of", "2026-10-14"]
    assert main(args) == 1
    out = capsys.readouterr().out
    assert "CRM.CUSTOMER [tier1] fail" in out and "-> OR-01" in out

    store = Store(db)
    run = store.query("SELECT r.run_id, c.cluster_id FROM validation_run r JOIN mismatch_cluster c "
                      "ON c.run_id = r.run_id WHERE r.level = 'L3'")[0]
    store.close()
    assert main(["validation", "accept", "--db", str(db), "--run", run["run_id"], "--cluster", run["cluster_id"],
                 "--approver", "jane@client", "--review-by", "2026-12-31", "--description", "policy A",
                 "--as-of", "2026-10-14"]) == 0
    capsys.readouterr()
    assert main(["validation", "summary", "--db", str(db), "--as-of", "2026-10-14", "--format", "json"]) == 0
    summ = json.loads(capsys.readouterr().out)
    assert summ["overall"] == "ready"
    assert summ["tiers"][0]["accepted_deviations"][0]["approver"] == "jane@client"

    assert main(["validation", "suite", "--config", str(cfg)]) == 0
    suites = json.loads(capsys.readouterr().out)
    assert [c["level"] for c in suites[0]["checks"]] == ["L0", "L1", "L2", "L3"]
    assert main(["validation", "levels", "--tier", "tier2"]) == 0
    assert "L3=sample" in capsys.readouterr().out
