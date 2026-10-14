from datetime import datetime

import pytest

from altitude.synthetic import AccountSpec, generate
from altitude_agents.telemetry import Telemetry

# A Thursday inside every change window; injected so logs and limits are deterministic.
CLOCK = datetime(2026, 10, 1, 10, 0, 0)


def clock() -> datetime:
    return CLOCK


@pytest.fixture(scope="session")
def seeded_tables():
    return generate(AccountSpec(days=35)).tables


@pytest.fixture(scope="session")
def seeded_tel(seeded_tables):
    return Telemetry.from_tables(seeded_tables)


@pytest.fixture(scope="session")
def snapshot_tel(seeded_snapshot):
    snap, _ = seeded_snapshot
    return Telemetry.from_snapshot(snap)
