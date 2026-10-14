"""Agent-fleet exceptions (``ApprovalRequired`` comes from core and is re-exported)."""

from __future__ import annotations

from altitude.core.errors import AltitudeError, ApprovalRequired, ReadOnlyViolation  # noqa: F401


class ActionRefused(AltitudeError):
    """An action is outside the tenant's pre-approved catalogue, scope, blast radius or change window."""


class AutonomyViolation(AltitudeError):
    """An agent attempted something above its (tenant-capped) autonomy level."""


class PromotionBlocked(AltitudeError):
    """An agent version failed its evaluation suite (or regressed) and cannot be promoted."""


class AgentNotPromoted(AltitudeError):
    """No promoted (eval-passed) version exists for the agent being run."""


class UnsupportedStatement(AltitudeError):
    """The simulated executor received SQL outside the action-template vocabulary."""


class ToolScopeViolation(AltitudeError):
    """An agent called a tool outside its declared minimal tool scope."""
