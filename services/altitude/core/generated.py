"""Generated artifacts (principle 8): renderings of the tool-neutral source of truth.

Every generated file starts with an ``AUTO-GENERATED — DO NOT EDIT`` header in
the file type's comment syntax. ``tools/check_generated.py`` re-runs every
registered generator and fails CI if the committed ``generated/`` tree differs.

Modules register generators by exposing ``generate() -> dict[relpath, content]``
in ``altitude.<module>.generate``; see ``GENERATOR_MODULES``.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Callable

from .paths import generated_dir

STAMP = "AUTO-GENERATED — DO NOT EDIT"

_COMMENT = {
    ".sql": "-- {}",
    ".tf": "# {}",
    ".py": "# {}",
    ".yaml": "# {}",
    ".yml": "# {}",
    ".sh": "# {}",
    ".md": "<!-- {} -->",
    ".html": "<!-- {} -->",
    ".csv": "# {}",
    ".json": None,  # JSON has no comments: stamped via a "_generated" key instead
}

# Modules whose ``generate`` submodule contributes to ``generated/``.
GENERATOR_MODULES = [
    "altitude.knowledge_publish.generate",
    "altitude.validation.generate",
    "altitude.diagnostics.generate",
    "altitude.observability.generate",
    "altitude.foundation.generate",
    "altitude.airready.generate",
    "altitude_agents.generate",
    "altitude.etl.generate",
    "altitude_connectors.generate",
    "altitude.packaging.generate",
]


def header(suffix: str, source: str) -> str:
    fmt = _COMMENT.get(suffix, "# {}")
    if fmt is None:
        return ""
    return fmt.format(f"{STAMP}. Source: {source}. Regenerate with `altitude generate`.") + "\n"


def stamp(content: str, suffix: str, source: str) -> str:
    if suffix == ".json":
        import json

        obj = json.loads(content)
        obj = {"_generated": f"{STAMP}. Source: {source}", **obj}
        return json.dumps(obj, indent=2, sort_keys=False, ensure_ascii=False) + "\n"
    if content.startswith("#!"):
        first, _, rest = content.partition("\n")
        return first + "\n" + header(suffix, source) + rest
    return header(suffix, source) + content


def is_stamped(text: str) -> bool:
    head = "\n".join(text.splitlines()[:3])
    return STAMP in head


def collect(modules: list[str] | None = None) -> dict[str, str]:
    """Run every registered generator; returns {relpath: content}."""
    out: dict[str, str] = {}
    for name in modules or GENERATOR_MODULES:
        try:
            mod = importlib.import_module(name)
        except ModuleNotFoundError as e:
            if e.name and name.startswith(e.name):
                continue
            raise
        gen: Callable[[], dict[str, str]] = getattr(mod, "generate")
        for rel, content in gen().items():
            if rel in out:
                raise ValueError(f"generated path {rel} produced by more than one generator")
            out[rel] = content
    return out


def write_all(root: Path | None = None) -> list[str]:
    root = root or generated_dir()
    written = []
    for rel, content in sorted(collect().items()):
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        written.append(rel)
    return written


def diff(root: Path | None = None) -> list[str]:
    """Return a list of problems: missing, changed, unstamped or orphaned generated files."""
    root = root or generated_dir()
    expected = collect()
    problems = []
    for rel, content in sorted(expected.items()):
        path = root / rel
        if not path.exists():
            problems.append(f"missing: generated/{rel}")
        elif path.read_text() != content:
            problems.append(f"stale: generated/{rel} (regenerate with `altitude generate`)")
        if not is_stamped(content):
            problems.append(f"unstamped: generated/{rel}")
    if root.exists():
        for path in sorted(root.rglob("*")):
            if path.is_file() and path.name != "README.md":
                rel = path.relative_to(root).as_posix()
                if rel not in expected:
                    problems.append(f"orphaned: generated/{rel} (no generator produces it)")
    return problems
