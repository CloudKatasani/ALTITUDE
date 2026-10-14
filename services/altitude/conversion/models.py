"""Tool-neutral conversion results shared by the SnowConvert wrapper and the sqlglot fallback."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Issue:
    """One conversion issue (EWI / FDM / PRF / OOS) as reported by a converter.

    ``line`` is the line in the *converted* output where the issue marker sits (``None`` when unknown);
    ``source_line`` is the line in the source file the tool reported.
    """

    code: str
    category: str              # EWI|FDM|PRF|OOS
    severity: str              # P1..P4
    message: str
    file: str                  # source path relative to the input root
    source_line: int | None = None
    line: int | None = None
    column: int | None = None
    snippet: str | None = None
    tool_severity: str | None = None
    known_issue: str | None = None
    detector_id: str | None = None
    region_end: int | None = None  # last output line of the statement the issue annotates, when known

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConvertedFile:
    source_rel: str            # path relative to the input root (posix)
    source_text: str
    output_text: str
    issues: list[Issue] = field(default_factory=list)


@dataclass
class ConversionOutput:
    tool: str                  # snowconvert|sqlglot
    tool_version: str
    dialect: str
    files: list[ConvertedFile] = field(default_factory=list)
    assessment: list[dict[str, Any]] = field(default_factory=list)
    log: str = ""

    @property
    def issues(self) -> list[Issue]:
        return [i for f in self.files for i in f.issues]
