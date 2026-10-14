import json
import shutil

import pytest
import yaml

from altitude.cli import main
from altitude.core.errors import ReadOnlyViolation
from altitude.core.generated import is_stamped
from altitude.core.knowledge import validate_tree
from altitude.core.paths import knowledge_dir
from altitude_connectors.generate import generate
from altitude_connectors.manifest import READ_PRIVILEGES, assert_read_only, available_sources, load_manifest


@pytest.mark.parametrize("source", ["sqlserver", "oracle", "teradata"])
def test_published_manifests_request_only_read_privileges(source):
    m = load_manifest(source)
    assert m.doc["row_data"] is False
    assert {g["privilege"] for g in m.grants} <= READ_PRIVILEGES
    assert all(len(g["why"]) > 10 for g in m.grants)
    assert m.scope and all(o["why"] for o in m.doc["objects_read"])


def test_manifest_with_write_privilege_fails_schema_validation_and_loader(tmp_path):
    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir(), root)
    path = root / "connectors" / "sqlserver.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["required_grants"].append({"privilege": "INSERT", "on": "dbo.FactSales", "why": "would allow writing to source"})
    path.write_text(yaml.safe_dump(doc))
    problems = validate_tree(root)
    assert any("connectors/sqlserver.yaml" in p and "required_grants" in p for p in problems)
    with pytest.raises(ReadOnlyViolation):
        assert_read_only(doc)
    with pytest.raises(ReadOnlyViolation):
        assert_read_only({**yaml.safe_load((knowledge_dir() / "connectors/oracle.yaml").read_text()), "row_data": True})


def test_generated_manifest_renderings_are_stamped():
    out = generate()
    assert set(out) == {f"connectors/{s}_{k}" for s in available_sources() for k in ("permissions.md", "grants.sql")}
    assert all(is_stamped(v) for v in out.values())
    assert "GRANT VIEW DEFINITION TO altitude_harvest;" in out["connectors/sqlserver_grants.sql"]
    assert "Row data read: **never**" in out["connectors/teradata_permissions.md"]


def test_cli_check_sql(capsys):
    assert main(["connectors", "check-sql", "SELECT name FROM sys.objects", "--source", "sqlserver"]) == 0
    assert json.loads(capsys.readouterr().out)["objects"] == ["sys.objects"]
    assert main(["connectors", "check-sql", "SELECT 1; DROP TABLE t", "--dialect", "tsql"]) == 2
    assert json.loads(capsys.readouterr().out)["verdict"] == "refused"
    assert main(["connectors", "check-sql", "SELECT * FROM dbo.DimCustomer", "--source", "sqlserver"]) == 2
    capsys.readouterr()
    assert main(["connectors", "manifest", "oracle", "--format", "grants"]) == 0
    assert "SELECT_CATALOG_ROLE" in capsys.readouterr().out


def test_cli_harvest_from_duckdb_catalog_file(td, tmp_path, capsys):
    db = tmp_path / "td_catalog.duckdb"
    con = td.build()
    con.execute(f"ATTACH '{db}' AS f")
    con.execute("COPY FROM DATABASE memory TO f")
    con.execute("DETACH f")
    con.close()
    rc = main(["connectors", "harvest", "--source", "teradata", "--engagement", "ENG-CLI", "--system", "TDPROD",
               "--duckdb", str(db), "--scripts", str(td.BTEQ_DIR), "--out", str(tmp_path / "snaps"),
               "--as-of", td.AS_OF.isoformat(), "--store", str(tmp_path / "store.duckdb")])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["counts"]["source_object"] == 17 and out["snapshot_id"].startswith("HRV-")
