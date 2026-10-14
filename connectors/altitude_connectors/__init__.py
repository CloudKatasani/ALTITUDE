"""Read-only source connectors and the extraction agent (M2, Section 29.2).

- :mod:`.readonly`  — the only path to a source: vetted read statements, logged
- :mod:`.manifest`  — published permission manifests (``knowledge/connectors``)
- :mod:`.harvest`   — SQL Server, Oracle and Teradata harvesters → canonical rows
- :mod:`.agent`     — the extraction agent: harvest locally, ship metadata only
"""

from .agent import ExtractionAgent, assert_metadata_only  # noqa: F401
from .canonical import CANONICAL_TABLES, HarvestBundle  # noqa: F401
from .manifest import Manifest, load_manifest  # noqa: F401
from .readonly import ReadOnlyConnection, StatementLog, classify_statement, read_only  # noqa: F401
