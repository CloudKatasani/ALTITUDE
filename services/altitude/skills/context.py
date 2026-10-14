"""Execution context passed to skills: control-plane store, workspace and rubric set."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from altitude.core.rubric import RubricSet, default_rubrics
from altitude.core.store import Store


@dataclass
class SkillContext:
    store: Store
    workspace: Path
    rubrics: RubricSet = field(default_factory=default_rubrics)
    extras: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_workspace(cls, workspace: str | Path) -> "SkillContext":
        ws = Path(workspace)
        ws.mkdir(parents=True, exist_ok=True)
        return cls(store=Store(str(ws / "control.duckdb")), workspace=ws)


def coerce(context: Any) -> SkillContext:
    """Accept the API's Context or a SkillContext (or None for an in-memory one)."""
    if isinstance(context, SkillContext):
        return context
    if context is None:
        import tempfile

        return SkillContext(store=Store(), workspace=Path(tempfile.mkdtemp(prefix="altitude-skill-")))
    return SkillContext(store=context.store, workspace=Path(context.workspace), extras=getattr(context, "extras", {}))
