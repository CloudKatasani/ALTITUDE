"""Planning & estimation (M4): wave clustering under wave rules as data, the factory state machine,
the pattern recommender, the estimation engine and readiness gates — all reading sealed snapshots and
recording ``snapshot_id`` + ``rubric_version``."""

from altitude.core.store import register_append_only

register_append_only("factory_transition")

from .context import PlanningContext  # noqa: E402
from .estimation import Estimate, Estimator, calibration_proposals, record_estimate  # noqa: E402
from .factory import Factory, InvalidTransition  # noqa: E402
from .gates import collect_metrics, evaluate_gate, gate_passed, record_gate  # noqa: E402
from .recommender import Recommendation, evidence_inputs, recommend  # noqa: E402
from .waves import WavePlan, WavePlanner, record_plan, validate_plan  # noqa: E402

__all__ = ["Estimate", "Estimator", "Factory", "InvalidTransition", "PlanningContext", "Recommendation", "WavePlan",
           "WavePlanner", "calibration_proposals", "collect_metrics", "evaluate_gate", "evidence_inputs",
           "gate_passed", "recommend", "record_estimate", "record_gate", "record_plan", "validate_plan"]
