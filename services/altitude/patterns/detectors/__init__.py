"""Detector registry.

Every known issue's ``detection.detector`` (and ``extra_detectors``) names a detector
registered here:

- ``static.<name>``  ``f(ctx: SourceContext, rubrics) -> Iterable[Finding]`` over source code;
- ``profile.<name>`` ``f(profile: dict, rubrics) -> Iterable[Finding]`` over harvested
  metadata and aggregate statistics (never row data). See :mod:`.profile` for the format.

Detectors report a *strength* (strong/medium/weak); the numeric confidence comes from
``rubric.patterns.detector_confidence`` so no confidence lives in code.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Callable, Iterable

from ..model import Finding

_MODULES = ("common", "teradata", "oracle", "sqlserver", "netezza_redshift", "profile")


@dataclass(frozen=True)
class Detector:
    name: str
    kind: str          # static | profile
    description: str
    func: Callable[..., Iterable[Finding]]


REGISTRY: dict[str, Detector] = {}


def _register(kind: str, name: str, description: str):
    full = f"{kind}.{name}"

    def deco(func: Callable[..., Iterable[Finding]]):
        if full in REGISTRY:
            raise ValueError(f"detector {full} registered twice")
        REGISTRY[full] = Detector(full, kind, description, func)
        return func

    return deco


def static(name: str, description: str):
    return _register("static", name, description)


def profile(name: str, description: str):
    return _register("profile", name, description)


_loaded = False


def ensure_loaded() -> dict[str, Detector]:
    global _loaded
    if not _loaded:
        for m in _MODULES:
            importlib.import_module(f"{__name__}.{m}")
        _loaded = True
    return REGISTRY


def get(name: str) -> Detector:
    reg = ensure_loaded()
    if name not in reg:
        raise KeyError(f"unknown detector {name!r}")
    return reg[name]


def hit(match, strength: str, message: str, rationale: str) -> Finding:
    """Finding from a :class:`~altitude.patterns.source.Match`."""
    return Finding(match.line, match.snippet, message, strength, rationale)
