"""Sherpa (AI delivery partner), specialist advisors and the Architecture Review Board (Section 17).

Everything here is grounded: answers cite evidence IDs from the engagement
snapshot and Pattern Library, and Sherpa refuses when the evidence does not
support an answer. Challenge rules, next actions and review-board lenses are
data in ``knowledge/advisory``.
"""

from .grounding import GroundingDoc, GroundingIndex  # noqa: F401
from .sherpa import Answer, Sherpa  # noqa: F401
from .review_board import ReviewBoard  # noqa: F401
