"""Fleet v1 agents (M10). Each implementation reads telemetry only through its scoped tools."""

from .access_hygiene import AccessHygiene
from .cost_sentinel import CostSentinel
from .dq_incident import DQIncident
from .pipeline_triage import PipelineTriage
from .release_watcher import ReleaseChangeWatcher
from .warehouse_rightsizer import WarehouseRightsizer

AGENTS = {
    CostSentinel.agent_id: CostSentinel,
    WarehouseRightsizer.agent_id: WarehouseRightsizer,
    PipelineTriage.agent_id: PipelineTriage,
    AccessHygiene.agent_id: AccessHygiene,
    DQIncident.agent_id: DQIncident,
    ReleaseChangeWatcher.agent_id: ReleaseChangeWatcher,
}

__all__ = ["AGENTS", "AccessHygiene", "CostSentinel", "DQIncident", "PipelineTriage", "ReleaseChangeWatcher",
           "WarehouseRightsizer"]
