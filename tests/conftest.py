import pytest

from altitude.synthetic import AccountSpec, build_snapshot


@pytest.fixture(scope="session")
def seeded_snapshot(tmp_path_factory):
    """Sealed synthetic snapshot with every seeded issue, plus its ground truth."""
    snap, account = build_snapshot(tmp_path_factory.mktemp("snap_seeded"), AccountSpec())
    return snap, account


@pytest.fixture(scope="session")
def clean_snapshot(tmp_path_factory):
    snap, account = build_snapshot(tmp_path_factory.mktemp("snap_clean"), AccountSpec(profile="clean"))
    return snap, account
