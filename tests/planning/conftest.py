import importlib.util
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SYSTEMS = {"sqlserver": "SalesDW", "oracle": "ORAPROD", "teradata": "TDPROD"}
INPUTS = {"deadline_weeks": 40, "appetite_for_change": 3, "model_quality_score": 60, "budget_band": "medium",
          "test_coverage": False, "start_date": "2026-11-02", "regulatory_objects": ["*RegulatoryFiling*"]}


def _estate(source: str):
    spec = importlib.util.spec_from_file_location(f"altitude_fixture_{source}_estate_plan",
                                                  FIXTURES / source / "estate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _no_patterns(fn, *a, **kw):
    mp = pytest.MonkeyPatch()
    mp.setitem(sys.modules, "altitude.patterns", None)
    try:
        return fn(*a, **kw)
    finally:
        mp.undo()


@pytest.fixture(scope="session")
def estates(tmp_path_factory):
    """{source: (harvest snapshot, assessment result)} for the three fixture estates."""
    from altitude.assessment import run_assessment
    from altitude_connectors import ExtractionAgent

    root = tmp_path_factory.mktemp("planning")
    out = {}
    for source, system in SYSTEMS.items():
        est = _estate(source)
        scripts = {"sqlserver": [est.HERE / "ssis"], "teradata": [est.HERE / "bteq"]}.get(source, [])
        agent = ExtractionAgent(source, est.build(), engagement_id=f"ENG-{source.upper()}", system_name=system,
                                script_dirs=scripts, execute_dialect="duckdb", as_of=est.AS_OF)
        harvest = agent.ship(snapshot_dir=root / source / "h")
        out[source] = (harvest, _no_patterns(run_assessment, harvest, root / source / "a"))
    return out


@pytest.fixture
def ctx_for(estates):
    from altitude.planning import PlanningContext

    def make(source: str = "sqlserver", **overrides):
        harvest, assessment = estates[source]
        return PlanningContext(assessment, harvest, inputs={**INPUTS, **overrides})

    return make


@pytest.fixture
def no_patterns():
    return _no_patterns
