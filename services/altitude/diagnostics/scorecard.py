"""Scorecard & maturity model (Section 6.11) and the next-package recommender (Section 6.13).

- Each evaluated check scores 1.0 when it passes; a failing check earns at most
  ``rubric.diagnostics.scorecard.failing_check_credit_max`` scaled by the share of compliant candidates.
- Domains (1–5) and WAF pillars (1–5) are severity-weighted means of their checks, banded by the rubric.
- The Platform Health Index (0–100) is the rubric-weighted mean of the evaluated domains.
Same outcomes + rubric version ⇒ identical numbers.
"""

from __future__ import annotations

from typing import Any, Iterable

from altitude.core.rubric import RubricSet

from .catalogue import Catalogue

RAW_DIGITS = 4


def _band(raw: float | None, bands: list[dict]) -> tuple[int | None, str | None]:
    if raw is None:
        return None, None
    for b in bands:
        if raw >= float(b["min"]):
            return int(b["score"]), str(b["label"])
    last = bands[-1]
    return int(last["score"]), str(last["label"])


def check_scores(outcomes: Iterable[Any], catalogue: Catalogue, rubrics: RubricSet) -> list[dict]:
    credit = float(rubrics.get("rubric.diagnostics.scorecard.failing_check_credit_max"))
    out = []
    for o in outcomes:
        check = catalogue.check(o.check_id)
        weight = float(rubrics.get(f"rubric.diagnostics.severity_weight.{check.severity}"))
        if o.status == "not_evaluated":
            score = None
        elif o.status == "pass":
            score = 1.0
        else:
            compliant = (o.candidates - o.flagged) / o.candidates if o.candidates else 0.0
            score = round(credit * compliant, RAW_DIGITS)
        out.append({"check_id": o.check_id, "title": check.title, "domain": check.domain,
                    "scored_domains": check.scored_domains, "waf_pillar": check.waf_pillar,
                    "severity": check.severity, "status": o.status, "candidates": o.candidates,
                    "flagged": o.flagged, "weight": weight, "score": score, "missing": list(o.missing)})
    return out


def _weighted(items: list[dict]) -> float | None:
    scored = [i for i in items if i["score"] is not None]
    total = sum(i["weight"] for i in scored)
    if not scored or not total:
        return None
    return round(sum(i["weight"] * i["score"] for i in scored) / total, RAW_DIGITS)


def compute_scorecard(outcomes: Iterable[Any], catalogue: Catalogue, rubrics: RubricSet, tier: str) -> dict:
    bands = rubrics.get("rubric.diagnostics.scorecard.bands")
    checks = check_scores(outcomes, catalogue, rubrics)
    scope = set(catalogue.tier(tier)["domains"])
    domains = []
    num = den = 0.0
    for d in catalogue.domains:
        in_scope = d["id"] in scope
        items = [c for c in checks if d["id"] in c["scored_domains"]] if in_scope else []
        raw = _weighted(items) if in_scope else None
        score, label = _band(raw, bands)
        weight = float(rubrics.get(d["weight_ref"]))
        if raw is not None:
            num += weight * raw
            den += weight
        domains.append({
            "id": d["id"], "name": d["name"], "waf_pillar": d["waf_pillar"], "in_scope": in_scope,
            "weight": weight, "raw": raw, "score": score, "label": label,
            "checks_evaluated": sum(1 for c in items if c["score"] is not None),
            "checks_failed": sum(1 for c in items if c["status"] == "fail"),
        })
    pillars = []
    for p in catalogue.pillars:
        items = [c for c in checks if c["waf_pillar"] == p["pillar"]]
        raw = _weighted(items)
        score, label = _band(raw, bands)
        pillars.append({"pillar": p["pillar"], "name": p["name"], "raw": raw, "score": score, "label": label,
                        "index": None if raw is None else round(raw * 100, 1),
                        "checks_evaluated": sum(1 for c in items if c["score"] is not None),
                        "checks_failed": sum(1 for c in items if c["status"] == "fail")})
    phi = round(100.0 * num / den, 1) if den else None
    return {"tier": tier, "platform_health_index": phi, "domains": domains, "pillars": pillars, "checks": checks}


def recommend(details: Iterable[Any], scorecard: dict, inputs: dict, catalogue: Catalogue, rubrics: RubricSet) -> list[dict]:
    flagged: dict[str, Any] = {}
    for d in details:
        flagged.setdefault(d.record["check_id"], d)
    out = []
    domain_scores = {d["id"]: d["score"] for d in scorecard["domains"]}
    for rule in catalogue.recommendations:
        when = rule["when"]
        ok = True
        evidence: list[str] = []
        if "checks_any" in when:
            hits = sorted(c for c in when["checks_any"] if c in flagged)
            ok &= len(hits) >= int(rubrics.get(when["min_checks_ref"]))
            evidence += hits
        if "domains_any" in when:
            hits = sorted(c for c, d in flagged.items()
                          if catalogue.check(c).domain in when["domains_any"]
                          and (not when.get("severity") or catalogue.check(c).severity == when["severity"]))
            ok &= len(hits) >= int(rubrics.get(when["min_checks_ref"]))
            evidence += hits
        if "client_input_list" in when:
            items = inputs.get(when["client_input_list"]) or []
            ok &= len(items) >= int(rubrics.get(when["min_items_ref"]))
            evidence += [f"CLIENT_INPUTS.{when['client_input_list']}"] if items else []
        if "domain_score_max" in when:
            spec = when["domain_score_max"]
            score = domain_scores.get(spec["domain"])
            ok &= score is not None and score <= int(rubrics.get(spec["score_ref"]))
            evidence += [f"{spec['domain']} score {score}"] if score is not None else []
        if ok:
            out.append({"id": rule["id"], "package": rule["package"], "pattern": rule["pattern"],
                        "evidence": sorted(set(evidence))})
    return out
