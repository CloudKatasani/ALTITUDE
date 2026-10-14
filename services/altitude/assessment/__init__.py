"""Assessment engine (M3): disposition, complexity, anti-patterns, drift risk.

Reads a sealed harvest snapshot (``altitude_connectors``), writes a sealed
assessment snapshot and optional control-plane rows; exports Markdown/HTML
reports and a CSV inventory from the assessment snapshot only.
"""

from .engine import AssessmentResult, assess, load_assessment, record, run_assessment  # noqa: F401
