"""Package D — Platform Deep Diagnostics (Section 6).

- ``bootstrap``  least-privilege access bootstrap, teardown and permission manifest (no ACCOUNTADMIN)
- ``harvest``    read-only live harvester (any DB-API connection) → sealed snapshot (harvest contract)
- ``catalogue``  check catalogue / domains / tiers / recommender loaded from ``knowledge/diagnostics``
- ``engine``     suggestion engine (signals → rules → clusters → value → remediation → narrative → review → priority)
- ``scorecard``  10-domain scorecard, WAF pillar roll-up, Platform Health Index, next-package recommender
- ``lifecycle``  persistence (migration 0100) and the proposed → accepted → implemented → value_realised | rejected flow
- ``exports``    every deliverable from one sealed snapshot (CSV/XLSX/Jira/ADO/PR pack/deck/report/savings model)
"""

from .catalogue import Catalogue, Check, default_catalogue  # noqa: F401
from .engine import DiagnosticResult, DiagnosticsEngine, run  # noqa: F401
