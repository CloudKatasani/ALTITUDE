from datetime import date

import pytest

from altitude.observability.config import load_golden
from altitude.observability.db import ObsDatabase
from altitude.observability.harvest import harvest_account
from altitude.observability.kpi import compute_kpis
from altitude.observability.sources import SyntheticSource
from altitude.synthetic import AccountSpec

END = date(2026, 9, 30)
ANOMALY_DAY = date(2026, 9, 29)  # a Tuesday


def build(spec: AccountSpec, retention: int | None = None, as_of: date | None = None) -> ObsDatabase:
    db = ObsDatabase()
    harvest_account(db, SyntheticSource(spec, native_retention_days=retention or spec.days), as_of or spec.end_date)
    compute_kpis(db)
    return db


@pytest.fixture(scope="session")
def obs_seeded():
    """OBS database over the golden-question fixture account (seeded profile, 45 days)."""
    fx = load_golden_fixture()
    return build(AccountSpec(account_name=fx["account_name"], profile=fx["profile"],
                             end_date=date.fromisoformat(fx["end_date"]), days=fx["days"]))


@pytest.fixture(scope="session")
def obs_anomaly():
    """Clean account with a seeded credit anomaly on WH_DS (x3 activity on ANOMALY_DAY)."""
    return build(AccountSpec(profile="clean", end_date=END, days=45,
                             anomalies=[{"date": ANOMALY_DAY, "warehouse": "WH_DS", "factor": 3.0}]))


def load_golden_fixture() -> dict:
    import yaml

    from altitude.observability.config import obs_dir

    return yaml.safe_load((obs_dir() / "golden_questions.yaml").read_text())["fixture"]


@pytest.fixture(scope="session")
def golden():
    return load_golden()


@pytest.fixture
def obs_build():
    """Factory: harvest a synthetic account into a fresh OBS database and compute KPIs."""
    return build
