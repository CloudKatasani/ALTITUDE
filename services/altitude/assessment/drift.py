"""Drift-risk scan: semantic-drift known issues (Section 10.13) per code object.

Delegates to the Pattern Library's executable detectors,
``altitude.patterns.scan_sql(sql: str, dialect: str) -> list[DriftHit]``
(DriftHit: issue_id, severity, line, snippet, message, confidence, rationale).
That module ships separately; it is imported lazily and, when unavailable, the
scan is recorded as *skipped* (with the reason) instead of failing the
assessment — the assessment then states that drift risk was not assessed.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any, Callable

from altitude.core.ids import stable_id

from .estate import Estate

PATTERNS_MODULE = "altitude.patterns"


@dataclass
class DriftResult:
    status: str  # completed | partial | skipped
    reason: str | None = None
    hits: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)
    scanned: int = 0

    def counts_by_object(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for h in self.hits:
            sev = out.setdefault(h["object_id"], {})
            sev[h["severity"]] = sev.get(h["severity"], 0) + 1
        return out

    def summary(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason, "objects_scanned": self.scanned,
                "hits": len(self.hits), "errors": len(self.errors)}


def load_scanner() -> tuple[Callable[[str, str], list[Any]] | None, str | None]:
    try:
        mod = importlib.import_module(PATTERNS_MODULE)
    except ImportError as e:
        return None, f"{PATTERNS_MODULE} is not installed ({e.__class__.__name__}: {e})"
    scan = getattr(mod, "scan_sql", None)
    if not callable(scan):
        return None, f"{PATTERNS_MODULE} does not provide scan_sql(sql, dialect)"
    return scan, None


def _field(hit: Any, name: str) -> Any:
    return hit.get(name) if isinstance(hit, dict) else getattr(hit, name, None)


def scan(estate: Estate) -> DriftResult:
    scanner, reason = load_scanner()
    if scanner is None:
        return DriftResult(status="skipped", reason=reason)
    result = DriftResult(status="completed")
    for oid in sorted(estate.objects):
        obj = estate.objects[oid]
        if not obj.text:
            continue
        result.scanned += 1
        try:
            hits = list(scanner(obj.text, estate.dialect) or [])
        except Exception as e:  # one unparseable object must not sink the assessment
            result.errors.append({"object_id": oid, "error": f"{e.__class__.__name__}: {e}"})
            continue
        for h in hits:
            issue = str(_field(h, "issue_id"))
            line = _field(h, "line")
            result.hits.append({
                "hit_id": stable_id("DRH", oid, issue, line, _field(h, "snippet")),
                "object_id": oid, "fq_name": obj.fq_name, "issue_id": issue,
                "severity": str(_field(h, "severity")), "line": int(line) if line is not None else None,
                "snippet": _field(h, "snippet"), "message": _field(h, "message"),
                "confidence": round(float(_field(h, "confidence") or 0), 3), "rationale": _field(h, "rationale"),
            })
    if result.errors:
        result.status = "partial"
        result.reason = f"{len(result.errors)} object(s) could not be scanned"
    result.hits.sort(key=lambda h: h["hit_id"])
    return result
