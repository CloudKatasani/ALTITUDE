"""Source harvesters (Section 10): SQL Server first, then Oracle and Teradata."""

from __future__ import annotations

from .base import Harvester, ObjectIndex
from .oracle import OracleHarvester
from .sqlserver import SqlServerHarvester
from .teradata import TeradataHarvester

HARVESTERS: dict[str, type[Harvester]] = {
    "sqlserver": SqlServerHarvester,
    "oracle": OracleHarvester,
    "teradata": TeradataHarvester,
}


def harvester_for(source: str) -> type[Harvester]:
    try:
        return HARVESTERS[source.lower()]
    except KeyError:
        raise ValueError(f"no harvester for source {source!r}; available: {', '.join(sorted(HARVESTERS))}") from None


__all__ = ["HARVESTERS", "Harvester", "ObjectIndex", "OracleHarvester", "SqlServerHarvester", "TeradataHarvester",
           "harvester_for"]
