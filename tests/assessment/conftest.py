import importlib.util
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load_estate(source: str):
    path = FIXTURES / source / "estate.py"
    spec = importlib.util.spec_from_file_location(f"altitude_fixture_{source}_estate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def harvest_snapshot(source: str, directory: Path):
    from altitude_connectors import ExtractionAgent

    est = load_estate(source)
    scripts = {"sqlserver": [est.HERE / "ssis"], "teradata": [est.HERE / "bteq"]}.get(source, [])
    system = {"sqlserver": "SalesDW", "oracle": "ORAPROD", "teradata": "TDPROD"}[source]
    agent = ExtractionAgent(source, est.build(), engagement_id="ENG-A", system_name=system, script_dirs=scripts,
                            execute_dialect="duckdb", as_of=est.AS_OF)
    return agent.ship(snapshot_dir=directory)


@pytest.fixture(scope="session")
def harvests(tmp_path_factory):
    d = tmp_path_factory.mktemp("harvests")
    return {s: harvest_snapshot(s, d / s) for s in ("sqlserver", "oracle", "teradata")}


def without_patterns(fn, *args, **kw):
    """Run ``fn`` with the drift scanner pinned to 'unavailable' (results must not depend on installed modules).

    The patch is undone immediately so other modules' tests still see ``altitude.patterns`` when it exists.
    """
    mp = pytest.MonkeyPatch()
    mp.setitem(sys.modules, "altitude.patterns", None)
    try:
        return fn(*args, **kw)
    finally:
        mp.undo()


@pytest.fixture(scope="session")
def assessments(harvests, tmp_path_factory):
    from altitude.assessment import run_assessment

    d = tmp_path_factory.mktemp("assessments")
    return {s: without_patterns(run_assessment, h, d / s) for s, h in harvests.items()}


@pytest.fixture(scope="session")
def mssql_assessment(assessments):
    return assessments["sqlserver"]


@pytest.fixture
def no_drift():
    """``no_drift(fn, *args)`` runs fn with the drift scanner unavailable."""
    return without_patterns


@pytest.fixture
def estate_module():
    return load_estate
