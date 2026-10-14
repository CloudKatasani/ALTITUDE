"""Editable engagement facts: catalogue (``knowledge/advisory/facts.yaml``) and typed parsing.

Used by the portal's Engagement facts form and to validate catalogued keys on the API. Empty input
clears a fact (stored as null, which removes it from the current view).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from altitude.core.knowledge import load_yaml


def catalogue() -> list[dict]:
    return load_yaml("advisory/facts.yaml")["groups"]


def fact_specs() -> dict[str, dict]:
    return {f["key"]: f for g in catalogue() for f in g["facts"]}


def coerce(spec: dict, raw: Any) -> Any:
    """Convert a submitted value to the fact's type; ``None`` means "clear". Raises ``ValueError``."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    t = spec["type"]
    if t == "boolean":
        if isinstance(raw, bool):
            return raw
        v = str(raw).strip().lower()
        if v in ("yes", "true", "1", "on"):
            return True
        if v in ("no", "false", "0", "off"):
            return False
        raise ValueError("choose yes or no")
    if t in ("integer", "number"):
        try:
            v = int(str(raw).strip()) if t == "integer" else float(str(raw).strip())
        except ValueError:
            raise ValueError("enter a whole number" if t == "integer" else "enter a number") from None
        if "min" in spec and v < spec["min"]:
            raise ValueError(f"must be at least {spec['min']}")
        if "max" in spec and v > spec["max"]:
            raise ValueError(f"must be at most {spec['max']}")
        return v
    if t == "date":
        try:
            return date.fromisoformat(str(raw).strip()).isoformat()
        except ValueError:
            raise ValueError("use YYYY-MM-DD") from None
    if t == "choice":
        if str(raw) not in spec["choices"]:
            raise ValueError(f"choose one of {', '.join(spec['choices'])}")
        return str(raw)
    return str(raw).strip()


def parse(submitted: dict[str, Any], current: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Validate catalogued facts. Returns (changes, errors); unchanged values are not repeated."""
    specs = fact_specs()
    changes: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, raw in submitted.items():
        spec = specs.get(key)
        if spec is None:
            continue
        try:
            value = coerce(spec, raw)
        except ValueError as e:
            errors[key] = str(e)
            continue
        if value != current.get(key):
            changes[key] = value
    return changes, errors


def validate_api(facts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """API writes: catalogued keys are type-checked; other keys pass through unchanged."""
    specs = fact_specs()
    out, errors = {}, {}
    for key, raw in facts.items():
        if key in specs:
            try:
                out[key] = coerce(specs[key], raw)
            except ValueError as e:
                errors[key] = str(e)
        else:
            out[key] = raw
    return out, errors
