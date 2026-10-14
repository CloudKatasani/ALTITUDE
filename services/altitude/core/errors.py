"""Exception types used across the platform."""


class AltitudeError(Exception):
    """Base class for platform errors."""


class KnowledgeValidationError(AltitudeError):
    """A knowledge file failed schema or semantic validation.

    ``problems`` holds precise ``file:json-path: message`` strings.
    """

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("knowledge validation failed:\n  " + "\n  ".join(problems))


class RubricReferenceError(AltitudeError):
    """A ``rubric.*`` reference could not be resolved."""


class AppendOnlyViolation(AltitudeError):
    """An attempt was made to mutate an append-only table or sealed snapshot."""


class ApprovalRequired(AltitudeError):
    """An action requires a recorded human approver before it may proceed."""


class ReadOnlyViolation(AltitudeError):
    """A connector attempted a write against a source or production target."""
