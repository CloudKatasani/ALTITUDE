import importlib.util
from pathlib import Path

import pytest

from altitude.skills import run_skill
from altitude.skills.context import SkillContext

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


@pytest.fixture(scope="session")
def sctx(tmp_path_factory):
    """One skill workspace + control-plane store shared by the end-to-end skill tests."""
    return SkillContext.from_workspace(tmp_path_factory.mktemp("skills_ws"))


@pytest.fixture(scope="session")
def call(sctx):
    def _call(name: str, args: dict | None = None):
        return run_skill(name, args or {}, context=sctx)

    return _call


@pytest.fixture(scope="session")
def snowflake_snapshot(call):
    """A sealed synthetic Snowflake estate (seeded issues), registered in the store."""
    return call("build_synthetic_snapshot", {"days": 35})


@pytest.fixture(scope="session")
def mssql_harvest(call):
    return call("harvest_source", {"source": "sqlserver", "engagement_id": "ENG-SKILLS"})


@pytest.fixture(scope="session")
def teradata_harvest(call):
    return call("harvest_source", {"source": "teradata", "engagement_id": "ENG-SKILLS"})


@pytest.fixture(scope="session")
def mssql_assessment(call, mssql_harvest):
    return call("run_assessment", {"harvest_snapshot_id": mssql_harvest["snapshot_id"]})


@pytest.fixture
def estate_module():
    """``estate_module(source)`` loads the emulated legacy estate builder from tests/fixtures/<source>/estate.py."""

    def load(source: str):
        spec = importlib.util.spec_from_file_location(f"altitude_skills_fixture_{source}_estate",
                                                      FIXTURES / source / "estate.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    return load
