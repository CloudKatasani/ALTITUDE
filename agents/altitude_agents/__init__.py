"""ALTITUDE agent fleet (M10, Section 18).

- ``telemetry``  read-only access to harvest-contract tables (sealed snapshot / Package O / fixtures)
- ``tools``      minimal, scoped, logged read-only tools
- ``catalogue``  agent catalogue, action catalogue and tenant policies (knowledge-as-data)
- ``actions``    autonomy enforcement (L0-L3), approvals, pre-approved catalogue, guard + auto-rollback
- ``executor``   SimulatedSnowflake (tests) and LiveExecutor (DB-API) behind one interface
- ``runtime``    AgentRunner: runs an agent and writes the immutable run/action logs
- ``agents``     Cost Sentinel, Warehouse Rightsizer, Pipeline Triage, Access Hygiene, DQ Incident,
                 Release Change Watcher
- ``evals``      golden-incident eval suites and promotion gating
"""

from .actions import ActionGateway, ActionLog, ProposedAction  # noqa: F401
from .errors import ActionRefused, AgentNotPromoted, AutonomyViolation, PromotionBlocked  # noqa: F401
from .executor import LiveExecutor, SimulatedSnowflake  # noqa: F401
from .runtime import AgentRunner  # noqa: F401
from .telemetry import Telemetry  # noqa: F401
