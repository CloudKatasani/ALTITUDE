"""Generated renderings of the validation knowledge (``generated/validation/``)."""

from __future__ import annotations

from altitude.core.generated import stamp
from altitude.core.rubric import default_rubrics

from .config import LEVELS, default_knowledge


def _tier_levels_md() -> str:
    k = default_knowledge()
    rs = default_rubrics()
    tiers = list(k.tiers)
    lines = [
        "# Validation levels by table tier",
        "",
        f"Levels version {k.levels_version}. Modes: full · sample · none (Section 12.3).",
        "",
        "| Level | Check | " + " | ".join(tiers) + " |",
        "|---|---|" + "---|" * len(tiers),
    ]
    for lv in LEVELS:
        d = k.levels[lv]
        lines.append(f"| {lv} | {d['name']}: {d['description']} | " +
                     " | ".join(k.tiers[t]["levels"][lv] for t in tiers) + " |")
    lines += ["", "## Thresholds (rubric)", ""]
    for t in tiers:
        ref = k.tiers[t]["threshold_ref"]
        vals = rs.get(ref)
        lines.append(f"- **{t}** (`{ref}`): " + ", ".join(f"{key}={vals[key]}" for key in sorted(vals)))
    lines += ["", f"Sampling: L3 sample rate `rubric.validation.sampling.l3_sample_rate` = "
                  f"{rs.get('rubric.validation.sampling.l3_sample_rate')}; L2 sample partitions "
                  f"`rubric.validation.sampling.l2_sample_partitions` = "
                  f"{rs.get('rubric.validation.sampling.l2_sample_partitions')}."]
    return "\n".join(lines) + "\n"


def _normalisation_md() -> str:
    k = default_knowledge()
    lines = [
        "# Normalisation rules",
        "",
        f"Version {k.normalisation_version}. Applied identically on both sides before L2 aggregation and L3 "
        "hashing. `always` rules only canonicalise representation; policy rules are enabled per programme ADR.",
        "",
        "| Rule | Operation | Applies to | When | Linked issues | Description |",
        "|---|---|---|---|---|---|",
    ]
    for r in k.rules:
        when = "always" if r.always else f"policy `{r.policy}`"
        params = f" {r.params}" if r.params else ""
        lines.append(f"| {r.id} | `{r.op}`{params} | {', '.join(r.applies_to)} | {when} | "
                     f"{', '.join(r.linked_issues) or '—'} | {r.description} |")
    lines += ["", "## Triage signatures", "", "| Signature | Description | Known issue by source dialect |",
              "|---|---|---|"]
    for s in k.signatures.values():
        mapping = ", ".join(f"{d}→{i}" for d, i in sorted(s.issue_by_dialect.items())) or "— (human triage)"
        lines.append(f"| `{s.signature}` | {s.description} | {mapping} |")
    return "\n".join(lines) + "\n"


def generate() -> dict[str, str]:
    return {
        "validation/tier_levels.md": stamp(_tier_levels_md(), ".md",
                                           "knowledge/validation/levels.yaml, knowledge/rubrics/validation.yaml"),
        "validation/normalisation_rules.md": stamp(_normalisation_md(), ".md",
                                                   "knowledge/validation/normalisation.yaml, "
                                                   "knowledge/validation/triage_signatures.yaml"),
    }
