"""Repository locations. Overridable with ``ALTITUDE_HOME`` for packaged installs."""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("ALTITUDE_HOME")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "knowledge").is_dir() and (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def knowledge_dir() -> Path:
    return repo_root() / "knowledge"


def generated_dir() -> Path:
    return repo_root() / "generated"
