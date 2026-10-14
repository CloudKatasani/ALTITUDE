import pytest

from altitude.diagnostics import DiagnosticsEngine


@pytest.fixture(scope="session")
def seeded_result(seeded_snapshot):
    snap, _ = seeded_snapshot
    return DiagnosticsEngine().run(snap, tier="D2")


@pytest.fixture(scope="session")
def clean_result(clean_snapshot):
    snap, _ = clean_snapshot
    return DiagnosticsEngine().run(snap, tier="D2")
