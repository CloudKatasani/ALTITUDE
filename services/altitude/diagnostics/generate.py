"""Generated renderings under ``generated/diagnostics/`` (header-stamped, committed, checked in CI).

- ``bootstrap.sql`` / ``teardown.sql`` / ``permission_manifest.json`` — the access package handed to the client
- ``detectors/<CHECK>.sql`` — each detector rendered with its helpers and the rubric values bound to its parameters
- ``catalogue.json`` — check index (domain, pillar, severity, KPIs, last_verified) for other modules
"""

from __future__ import annotations

import json

from altitude.core.generated import stamp
from altitude.core.ids import content_hash
from altitude.core.rubric import RubricSet, default_rubrics

from .bootstrap import bootstrap_sql, permission_manifest, teardown_sql
from .catalogue import default_catalogue


def rubric_tag(rubrics: RubricSet) -> str:
    """Only the diagnostics namespace: other modules' rubric changes must not make these files stale."""
    return f"diagnostics@{rubrics.versions['diagnostics']}:{content_hash(rubrics.namespaces['diagnostics'], 10)}"


def _detector_sql(check, catalogue, rubrics) -> str:
    params = check.resolve_params(rubrics)
    sources = check.param_sources()
    lines = [
        f"-- {check.id}: {check.title}",
        f"-- Domain {check.domain} · WAF pillar {check.waf_pillar} · severity {check.severity} · "
        f"last verified {check.raw['last_verified']}",
        f"-- Source tables: {', '.join(check.requires)}",
        f"-- Rubric: {rubric_tag(rubrics)}",
        "-- Parameters (bound at run time; thresholds come from the rubric, never literals):",
    ]
    for name in check.referenced_params():
        if name in params:
            lines.append(f"--   ${name} = {json.dumps(params[name])}  ({sources[name]})")
        else:
            lines.append(f"--   ${name} = <bound by the engine from the snapshot / rubric units>")
    used = [h for h in catalogue.helpers if h["name"] in check.detector["signals"]]
    for h in used:
        lines.append(f"-- Helper {h['name']} ({h['id']}): {h['description']}")
    return "\n".join(lines) + "\n" + check.detector_sql() + ";\n"


def generate() -> dict[str, str]:
    rubrics = default_rubrics()
    catalogue = default_catalogue()
    out: dict[str, str] = {
        "diagnostics/bootstrap.sql": stamp(bootstrap_sql(rubrics=rubrics), ".sql", "altitude.diagnostics.bootstrap"),
        "diagnostics/teardown.sql": stamp(teardown_sql(), ".sql", "altitude.diagnostics.bootstrap"),
        "diagnostics/permission_manifest.json": stamp(json.dumps(permission_manifest(rubrics=rubrics), sort_keys=True),
                                                      ".json", "altitude.diagnostics.bootstrap"),
    }
    index = []
    for check in catalogue.checks:
        src = catalogue.sources[check.id]
        out[f"diagnostics/detectors/{check.id}.sql"] = stamp(_detector_sql(check, catalogue, rubrics), ".sql",
                                                             f"knowledge/{src}")
        index.append({"id": check.id, "title": check.title, "domain": check.domain, "waf_pillar": check.waf_pillar,
                      "severity": check.severity, "cluster_by": check.cluster_by,
                      "remediation": check.raw["remediation"]["type"], "autonomy": check.raw["remediation"]["autonomy"],
                      "kpis_to_watch": check.raw["kpis_to_watch"], "last_verified": check.raw["last_verified"],
                      "source": f"knowledge/{src}"})
    out["diagnostics/catalogue.json"] = stamp(json.dumps({"rubric": rubric_tag(rubrics), "checks": index}, sort_keys=True),
                                              ".json", "knowledge/diagnostics")
    return out
