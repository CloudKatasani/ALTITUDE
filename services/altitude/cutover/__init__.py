"""Cutover, coexistence and decommissioning (Section 13).

- :func:`build_go_no_go_pack` assembles the evidence pack from the canonical
  model (validation runs, accepted deviations, grant mappings, rollback
  rehearsals) plus supplied operational facts, evaluates the ``cutover_go``
  criteria and records a *recommendation* — the decision itself needs a named
  human (:func:`decide`).
- :func:`decommission_readiness` blocks decommissioning while legacy consumers
  are still active and produces the savings realisation report.
"""

from .pack import build_go_no_go_pack, decide, evaluate_criteria, render_markdown  # noqa: F401
from .decommission import decommission_readiness, savings_realisation  # noqa: F401
