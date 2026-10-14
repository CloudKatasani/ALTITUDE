"""Release Change Watcher (Section 18.2 #10, max L1): map behaviour-change bundle entries to the
client's actual usage (query text, view definitions, object settings) and recommend non-prod tests."""

from __future__ import annotations

from ..catalogue import load_behaviour_changes
from ..runtime import AgentContext, AgentResult, BaseAgent, Finding

LISTED = 10  # objects named inline in rationale/recommendation text (presentation only)


class ReleaseChangeWatcher(BaseAgent):
    agent_id = "AG-RELEASE-CHANGE-WATCHER"
    version = "1.0.0"

    def __init__(self, entries: list[dict] | None = None):
        self.entries = entries if entries is not None else load_behaviour_changes()

    def run(self, ctx: AgentContext) -> AgentResult:
        days = int(ctx.r("release_watcher.lookback_days"))
        min_matches = int(ctx.r("release_watcher.min_matches"))
        findings, clear = [], []
        for entry in self.entries:
            impacted: dict[str, dict] = {}
            direct = False
            for sig in entry["signatures"]:
                rows = ctx.call("usage_signature_scan", kind=sig["kind"], days=days, pattern=sig.get("pattern"),
                                sql=sig.get("sql"))
                direct = direct or sig["kind"] != "sql"
                for r in rows:
                    cur = impacted.setdefault(str(r["OBJECT_NAME"]), {"object": str(r["OBJECT_NAME"]), "matches": 0,
                                                                      "kind": sig["kind"], "example": r.get("DETAIL")})
                    cur["matches"] += int(r["MATCHES"] or 0)
            total = sum(x["matches"] for x in impacted.values())
            if not impacted or total < min_matches:
                clear.append(entry["id"])
                continue
            conf = float(ctx.r("release_watcher.confidence_direct_match" if direct
                               else "release_watcher.confidence_property_match"))
            objs = sorted(impacted)
            findings.append(Finding(
                kind="impact", subject=entry["id"],
                title=f"{entry['bundle']}: {entry['title']} — {len(objs)} impacted object(s)/signature(s)",
                confidence=conf,
                rationale=(f"{total} usage match(es) in the last {days} days for {entry['title']!r}: "
                           + ", ".join(objs[:LISTED]) + ("…" if len(objs) > LISTED else "")),
                detail={"bundle": entry["bundle"], "category": entry["category"], "impacted": objs,
                        "matches": total, "examples": [impacted[o] for o in objs[:5]]},
                evidence=[f"BEHAVIOUR_CHANGE:{entry['id']}"] + [f"USAGE:{o}" for o in objs],
                recommendation=f"{entry['test_guidance']} Impacted: {', '.join(objs[:LISTED])}"))
        return AgentResult(findings=findings,
                           summary=f"{len(findings)} bundle entr{'y' if len(findings) == 1 else 'ies'} impact this "
                                   f"account; {len(clear)} not applicable")
