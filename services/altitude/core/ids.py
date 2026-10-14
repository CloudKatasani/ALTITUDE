"""Deterministic identifiers and content hashing.

Reproducibility (same snapshot + rubric version => identical output) depends on
never using random IDs or wall-clock time inside computations.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any


def _default(o: Any) -> Any:
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if isinstance(o, Decimal):
        return str(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if hasattr(o, "model_dump"):
        return o.model_dump(mode="json")
    raise TypeError(f"not hashable as JSON: {type(o)!r}")


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_default)


def content_hash(obj: Any, length: int = 16) -> str:
    return hashlib.sha256(canonical_json(obj).encode()).hexdigest()[:length]


def stable_id(prefix: str, *parts: Any, length: int = 8) -> str:
    """``PREFIX-<hash>`` derived only from ``parts``."""
    return f"{prefix}-{content_hash(list(parts), length).upper()}"
