import sys
from pathlib import Path

import pytest

from altitude.conversion.fallback import SqlglotConverter
from altitude.conversion.orchestrator import ConversionOrchestrator
from altitude.conversion.remediation import RemediationAgent
from altitude.conversion.review import ReviewWorkflow
from altitude.core.store import Store

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "snowconvert"
SOURCES = FIXTURES / "source"
FAKE_SNOWCT = [sys.executable, str(FIXTURES / "fake_snowct.py")]


@pytest.fixture
def store():
    s = Store()
    yield s
    s.close()


@pytest.fixture
def converted(store, tmp_path):
    """Every fixture dialect converted with the sqlglot fallback and remediated into PR packs."""
    out = {}
    agent = RemediationAgent(store, packs_root=tmp_path / "packs")
    for dialect in ("teradata", "oracle", "tsql"):
        run = ConversionOrchestrator(store, "ENG-T", converter=SqlglotConverter()).run(
            SOURCES / dialect, dialect, tmp_path / "out")
        for artifact_id in run.artifact_ids:
            art = store.get("converted_artifact", artifact_id=artifact_id)
            out[art["target_path"]] = agent.remediate(artifact_id)
    return out


@pytest.fixture
def workflow(store):
    return ReviewWorkflow(store)
