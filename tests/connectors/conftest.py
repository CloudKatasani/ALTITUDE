import importlib.util
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_estate(source: str):
    """Import tests/fixtures/<source>/estate.py under a unique module name."""
    path = FIXTURES / source / "estate.py"
    spec = importlib.util.spec_from_file_location(f"altitude_fixture_{source}_estate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="session")
def mssql():
    return load_estate("sqlserver")


@pytest.fixture(scope="session")
def ora():
    return load_estate("oracle")


@pytest.fixture(scope="session")
def td():
    return load_estate("teradata")


@pytest.fixture(scope="session")
def mssql_agent(mssql):
    from altitude_connectors import ExtractionAgent

    agent = ExtractionAgent("sqlserver", mssql.build(), engagement_id="ENG-T", system_name="SalesDW",
                            script_dirs=[mssql.SSIS_DIR], execute_dialect="duckdb", as_of=mssql.AS_OF)
    agent.harvest()
    return agent


@pytest.fixture(scope="session")
def mssql_bundle(mssql_agent):
    return mssql_agent.bundle
