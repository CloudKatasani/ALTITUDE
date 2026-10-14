"""M7: landing-zone Terraform is structurally valid and enforces the role/warehouse policy (terraform not required)."""

import copy
import re

import pytest

from altitude.core.errors import KnowledgeValidationError
from altitude.core.paths import generated_dir
from altitude.core.rubric import default_rubrics
from altitude.foundation import landing_zone, terraform, tflint
from altitude.foundation.generate import generate, terraform_files


@pytest.fixture(scope="module")
def lz():
    return landing_zone.load()


@pytest.fixture(scope="module")
def tf(lz):
    return terraform.build(lz)


def test_generated_terraform_is_committed_stamped_and_deterministic(tf, lz):
    out = generate()
    for name, body in tf.items():
        rel = f"foundation/terraform/{name}"
        assert out[rel].startswith("# AUTO-GENERATED — DO NOT EDIT")
        assert (generated_dir() / rel).read_text() == out[rel]
    assert terraform.build(landing_zone.load()) == tf


def test_generated_terraform_passes_structural_lint(tf, lz):
    assert tflint.lint(tf, database_regex=lz["naming"]["database_regex"]) == []


def test_every_reference_is_defined_and_blocks_balance(tf):
    resources, variables, problems, _ = tflint.parse(tf)
    assert problems == []
    defined = {r.address for r in resources}
    refs = {f"{a}.{b}" for body in tf.values() for a, b in tflint.REF_RE.findall(re.sub(r'"[^"]*"', '""', body))}
    assert refs and refs <= defined
    assert {"organization_name", "account_name", "private_key", "service_user_public_keys"} <= variables


def test_role_model_never_grants_object_privileges_to_users(tf, lz):
    resources, *_ = tflint.parse(tf)
    by_addr = {r.address: r for r in resources}
    types = {r.rtype for r in resources}
    assert not any(t.startswith("snowflake_grant_privileges_to_") and not t.endswith("account_role") for t in types)
    user_grants = [r for r in resources if r.rtype == "snowflake_grant_account_role" and "user_name" in r.attrs]
    assert user_grants
    for g in user_grants:
        role = by_addr[re.search(r"(snowflake_account_role\.[a-z0-9_]+)", g.attrs["role_name"]).group(1)]
        assert not role.str_attr("name").startswith("AR_")
    # every object privilege lands on an access role or a functional/agent role (warehouse usage only)
    for r in resources:
        if r.rtype == "snowflake_grant_privileges_to_account_role":
            target = by_addr[re.search(r"(snowflake_account_role\.[a-z0-9_]+)", r.attrs["account_role_name"]).group(1)]
            name = target.str_attr("name")
            if not name.startswith("AR_"):
                assert "WAREHOUSE" in r.address.upper() or "wh_" in r.address or "governance" in r.address


def test_every_warehouse_has_monitor_and_policy_auto_suspend(tf):
    resources, *_ = tflint.parse(tf)
    by_addr = {r.address: r for r in resources}
    whs = [r for r in resources if r.rtype == "snowflake_warehouse"]
    assert len(whs) == 5
    max_suspend = default_rubrics().get("rubric.compute.auto_suspend_max_seconds")
    for w in whs:
        mon = w.attrs["resource_monitor"].rsplit(".", 1)[0]
        assert by_addr[mon].rtype == "snowflake_resource_monitor"
        assert 1 <= int(w.attrs["auto_suspend"]) <= max_suspend
    assert any(r.rtype == "snowflake_execute" and "RESOURCE_MONITOR" in r.attrs["execute"] for r in resources)


def test_role_hierarchy_and_naming(lz):
    assert len(lz.databases) == 16 and all(re.match(lz["naming"]["database_regex"], d.name) for d in lz.databases)
    assert lz.functional_access["FR_BI"] == ["AR_PROD_SALES_SEMANTIC_RO", "AR_PROD_FINANCE_SEMANTIC_RO"]
    assert all(r.endswith("_RW") for r in lz.functional_access["FR_ENGINEER"])
    assert {a["role"] for a in lz.agent_identities} >= {"ALT_AGENT_RIGHTSIZER", "ALT_AGENT_ACCESS_HYGIENE"}


@pytest.mark.parametrize("mutate,expected", [
    (lambda f: f.update({"warehouses.tf": f["warehouses.tf"].replace(
        'resource "snowflake_resource_monitor" "rm_wh_elt"', 'resource "snowflake_resource_monitor" "rm_wh_elt_old"')}),
     "undefined resource snowflake_resource_monitor.rm_wh_elt"),
    (lambda f: f.update({"warehouses.tf": f["warehouses.tf"].replace("auto_suspend                 = 60",
                                                                      "auto_suspend                 = 3600", 1)}),
     "auto_suspend 3600 outside"),
    (lambda f: f.update({"x.tf": 'resource "snowflake_grant_privileges_to_user" "bad" {\n  user_name = "JSMITH"\n}\n'}),
     "never to users"),
    (lambda f: f.update({"x.tf": 'resource "snowflake_grant_account_role" "bad" {\n'
                                 '  role_name = snowflake_account_role.ar_prod_sales_raw_rw.name\n'
                                 '  user_name = snowflake_service_user.svc_dbt.name\n}\n'}),
     "not access role 'AR_PROD_SALES_RAW_RW'"),
    (lambda f: f.update({"x.tf": 'resource "snowflake_database" "bad" {\n  name = "SALES_DB"\n'}),
     "never closed"),
    (lambda f: f.update({"x.tf": 'resource "snowflake_database" "legacy" {\n  name = "SALES_DB"\n}\n'}),
     "naming convention"),
    (lambda f: f.update({"x.tf": 'resource "snowflake_warehouse" "rogue" {\n  name = "WH_ROGUE"\n  auto_suspend = 60\n'
                                 '  auto_resume = "true"\n  statement_timeout_in_seconds = 600\n}\n'}),
     "no resource monitor"),
])
def test_linter_catches_violations(tf, lz, mutate, expected):
    files = copy.deepcopy(tf)
    mutate(files)
    problems = tflint.lint(files, database_regex=lz["naming"]["database_regex"])
    assert any(expected in p for p in problems), problems


def test_landing_zone_semantic_validation_is_precise(lz):
    bad = copy.deepcopy(lz.doc)
    bad["users"][0]["functional_roles"] = ["AR_PROD_SALES_RAW_RW"]
    bad["warehouses"][0]["auto_suspend"] = 600
    bad["governance"]["masking"][0]["tag"] = "NOT_A_TAG"
    problems = landing_zone.validate(landing_zone._expand(bad, None))
    assert any("SVC_DBT: unknown functional role AR_PROD_SALES_RAW_RW" in p for p in problems)
    assert any("WH_ELT: auto_suspend 600s exceeds rubric.compute.auto_suspend_max_seconds" in p for p in problems)
    assert any("unknown tag NOT_A_TAG" in p for p in problems)


def test_strict_load_raises_on_invalid_model(tmp_path):
    import shutil

    from altitude.core.paths import knowledge_dir
    root = tmp_path / "knowledge"
    shutil.copytree(knowledge_dir() / "foundation", root / "foundation")
    shutil.copytree(knowledge_dir() / "agents", root / "agents")
    text = (root / "foundation/landing_zone.yaml").read_text().replace("functional_roles: [FR_BI]",
                                                                         "functional_roles: [FR_NOPE]")
    (root / "foundation/landing_zone.yaml").write_text(text)
    with pytest.raises(KnowledgeValidationError, match="FR_NOPE"):
        landing_zone.load(root)


def test_terraform_files_helper_matches_generator():
    assert set(terraform_files()) == {p.split("/")[-1] for p in generate() if p.startswith("foundation/terraform/")}
