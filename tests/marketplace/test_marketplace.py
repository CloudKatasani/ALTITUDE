import copy

import sqlglot

from altitude.core.generated import is_stamped
from altitude.marketplace import agents, assess, products
from altitude.marketplace.generate import generate
from altitude.marketplace.render import agent_spec, listing_manifest


def _by(items):
    return {x["id"]: x for x in items}


def test_certification_is_evidence_based_on_the_seeded_estate(seeded_snapshot):
    snap, _ = seeded_snapshot
    r = assess(snap, package_o=True)
    p = _by(r["products"])
    assert p["DP-ORDERS"]["certified"]
    cust = p["DP-CUSTOMER-360"]
    assert not cust["certified"] and cust["blockers"] == ["privacy"] and "DX-SEC-05" in cust["fixes"]
    assert any("DIM_CUSTOMER.EMAIL" in c["detail"] for c in cust["checks"] if not c["passed"])
    rev = p["DP-REVENUE"]
    assert not rev["certified"] and {"DX-GOV-01", "DX-GOV-02", "DX-REL-02"} <= set(rev["fixes"])
    a = _by(r["agents"])
    assert not a["MA-REVENUE-ANALYST"]["ready"]
    assert any("DP-REVENUE" in c["detail"] for c in a["MA-REVENUE-ANALYST"]["checks"] if not c["passed"])
    assert all("DX-AI-02" in x["fixes"] for x in r["agents"])  # no Cortex budget in the seeded estate


def test_remediated_estate_certifies_and_unblocks_agents(clean_snapshot):
    snap, _ = clean_snapshot
    r = assess(snap, package_o=True)
    p, a = _by(r["products"]), _by(r["agents"])
    assert p["DP-REVENUE"]["certified"] and p["DP-CUSTOMER-360"]["certified"]
    assert a["MA-REVENUE-ANALYST"]["ready"] and a["MA-POLICY-SEARCH"]["ready"]
    assert not assess(snap, package_o=False) is None
    assert not _by(assess(snap, package_o=False)["agents"])["MA-FINOPS-ADVISOR"]["ready"]


def test_assessment_is_reproducible(seeded_snapshot):
    snap, _ = seeded_snapshot
    assert assess(snap)["assessment_hash"] == assess(snap)["assessment_hash"]


def test_renderings_parse_and_are_stamped():
    out = generate()
    assert all(is_stamped(v) for v in out.values())
    for pid in (p["id"] for p in products()):
        sql = out[f"marketplace/products/{pid}.sql"]
        body = sql.split("CREATE ORGANIZATION LISTING")[0]
        for stmt in sqlglot.parse(body, read="snowflake"):
            assert stmt is not None
        assert "SECURE VIEW" in sql and "WITH MANAGED ACCESS" in sql
    p = products()[0]
    manifest = listing_manifest(p)
    assert p["owner"] in manifest and "data_dictionary" in manifest
    spec = agent_spec(agents()[0], _by(products()))
    assert spec["tools"][0]["tool_spec"]["type"] == "cortex_analyst_text_to_sql"
    assert spec["tool_resources"]["analyst"]["semantic_view"] == agents()[0]["semantic_view"]


def test_unknown_product_reference_is_a_knowledge_error(tmp_path):
    import shutil

    import yaml

    from altitude.core.knowledge import validate_tree
    from altitude.core.paths import knowledge_dir

    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir(), root)
    path = root / "marketplace" / "agents.yaml"
    doc = yaml.safe_load(path.read_text())
    bad = copy.deepcopy(doc["marketplace_agents"][0])
    bad["id"], bad["products"] = "MA-BROKEN", ["DP-NOPE"]
    doc["marketplace_agents"].append(bad)
    path.write_text(yaml.safe_dump(doc, sort_keys=False))
    assert any("MA-BROKEN consumes unknown product DP-NOPE" in p for p in validate_tree(root))
