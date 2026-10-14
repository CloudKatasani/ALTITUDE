"""Warehouse Rightsizer (Section 18.2 #2): auto-suspend at L3 (pre-approved catalogue, auto-revert if
queueing rises), size and cluster changes at L2 (drafts for owner approval)."""

from __future__ import annotations

from ..actions import ProposedAction
from ..executor import WAREHOUSE_SIZES
from ..runtime import AgentContext, AgentResult, BaseAgent, Finding


def _credits_per_hour(size: str) -> float:
    """Standard warehouse credit rate: XSMALL = 1 and each size step doubles it."""
    return float(2 ** WAREHOUSE_SIZES.index(size)) if size in WAREHOUSE_SIZES else 0.0


class WarehouseRightsizer(BaseAgent):
    agent_id = "AG-WAREHOUSE-RIGHTSIZER"
    version = "1.0.0"

    def run(self, ctx: AgentContext) -> AgentResult:
        days = int(ctx.r("rightsizer.window_days"))
        target_suspend = int(ctx.r("rightsizer.auto_suspend_target_seconds"))
        idle_min = float(ctx.r("rightsizer.idle_ratio_min"))
        cfg = ctx.call("warehouse_config")
        util = {r["WAREHOUSE_NAME"]: r for r in ctx.call("warehouse_utilisation", days=days)}
        load = {r["WAREHOUSE_NAME"]: r for r in ctx.call("warehouse_load", hours=days * 24)}
        prof = {r["WAREHOUSE_NAME"]: r for r in ctx.call("warehouse_query_profile", days=days)}
        findings: list[Finding] = []
        actions: list[ProposedAction] = []
        for w in cfg:
            name = w["WAREHOUSE_NAME"]
            u, ld, p = util.get(name), load.get(name, {}), prof.get(name, {})
            idle = float(u["IDLE_RATIO"]) if u else 0.0
            billed = float(u["BILLED"]) if u else 0.0
            queued_avg = float(ld.get("AVG_QUEUED") or 0.0)
            queued_peak = float(ld.get("PEAK_HOUR_QUEUED") or 0.0)
            p90 = float(p.get("P90_EXEC_MS") or 0.0)
            spill = float(p.get("SPILL_LOCAL") or 0) + float(p.get("SPILL_REMOTE") or 0)
            ev = [f"WAREHOUSES:{name}", f"WAREHOUSE_METERING_HISTORY:{name}:{days}d",
                  f"WAREHOUSE_LOAD_HISTORY:{name}:{days}d"]

            # ---- auto-suspend (L3 when pre-approved)
            if (w["AUTO_SUSPEND"] or 0) > target_suspend and idle >= idle_min:
                conf = float(ctx.r("rightsizer.confidence_auto_suspend"))
                saving = round(billed * idle * (1 - target_suspend / float(w["AUTO_SUSPEND"])), 2)
                f = Finding(kind="idle_auto_suspend", subject=name,
                            title=f"{name}: AUTO_SUSPEND {w['AUTO_SUSPEND']}s with {idle:.0%} idle billed compute",
                            confidence=conf,
                            rationale=(f"{idle:.0%} of {billed:.1f} billed compute credits over {days} days had no "
                                       f"attributed query work; AUTO_SUSPEND {w['AUTO_SUSPEND']}s exceeds the "
                                       f"{target_suspend}s target"),
                            detail={"auto_suspend": w["AUTO_SUSPEND"], "idle_ratio": round(idle, 4),
                                    "billed_credits": round(billed, 2), "est_credits_saved": saving},
                            evidence=ev)
                findings.append(f)
                actions.append(ProposedAction(
                    "warehouse.set_auto_suspend", name, {"auto_suspend": target_suspend}, "L3", conf, f.rationale,
                    ev, f"ALTER {name} AUTO_SUSPEND {w['AUTO_SUSPEND']} -> {target_suspend}", f.key))

            # ---- downsize (L2 draft)
            size = str(w["WAREHOUSE_SIZE"]).upper()
            if (_credits_per_hour(size) >= float(ctx.r("rightsizer.downsize_min_credits_per_hour"))
                    and p90 <= float(ctx.r("rightsizer.downsize_p90_exec_ms_max"))
                    and queued_avg <= float(ctx.r("rightsizer.downsize_queued_load_max")) and spill == 0
                    and size in WAREHOUSE_SIZES and WAREHOUSE_SIZES.index(size) > 0):
                smaller = WAREHOUSE_SIZES[WAREHOUSE_SIZES.index(size) - 1]
                conf = float(ctx.r("rightsizer.confidence_downsize"))
                f = Finding(kind="oversized", subject=name,
                            title=f"{name}: {size} with p90 execution {p90 / 1000:.1f}s and no queueing or spilling",
                            confidence=conf,
                            rationale=(f"p90 execution time {p90:.0f} ms, average queued load {queued_avg:.3f}, no "
                                       f"spilling over {days} days: the workload fits {smaller}"),
                            detail={"size": size, "proposed_size": smaller, "p90_exec_ms": p90,
                                    "avg_queued": round(queued_avg, 4)},
                            evidence=ev + [f"QUERY_HISTORY:{name}:{days}d"])
                findings.append(f)
                actions.append(ProposedAction("warehouse.resize", name, {"warehouse_size": smaller}, "L2", conf,
                                              f.rationale, f.evidence, f"Resize {name} {size} -> {smaller}", f.key))

            # ---- scale-out for queueing (L2 draft)
            if (queued_peak >= float(ctx.r("rightsizer.scale_out_queued_load_min"))
                    and (w["MAX_CLUSTER_COUNT"] or 1) < int(ctx.r("rightsizer.scale_out_max_clusters"))):
                conf = float(ctx.r("rightsizer.confidence_scale_out"))
                target_clusters = int(ctx.r("rightsizer.scale_out_max_clusters"))
                f = Finding(kind="queueing", subject=name,
                            title=f"{name}: peak-hour queued load {queued_peak:.2f} on {w['MAX_CLUSTER_COUNT']} cluster(s)",
                            confidence=conf,
                            rationale=(f"Peak hour-of-day average queued load {queued_peak:.2f} indicates concurrency "
                                       f"demand; scale out (multi-cluster) rather than up"),
                            detail={"peak_hour_queued": round(queued_peak, 4), "max_cluster_count": w["MAX_CLUSTER_COUNT"],
                                    "proposed_max_cluster_count": target_clusters},
                            evidence=ev)
                findings.append(f)
                actions.append(ProposedAction("warehouse.set_max_cluster_count", name,
                                              {"max_cluster_count": target_clusters}, "L2", conf, f.rationale, ev,
                                              f"Set {name} MAX_CLUSTER_COUNT -> {target_clusters}", f.key))
        return AgentResult(findings=findings, actions=actions,
                           summary=f"{len(actions)} rightsizing action(s) across {len(cfg)} warehouse(s)")
