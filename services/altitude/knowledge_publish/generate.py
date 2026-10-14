"""Generated renderings of the Pattern Library (``generated/knowledge_publish/``).

- ``known_issues.md``      known-issues catalogue (Appendix A fields) per dialect
- ``mappings.md``          conversion maps
- ``drift_checklist.md``   Section 10.13 checklist x dialect coverage matrix
- ``pattern_library.sql``  Snowflake DDL + INSERTs to publish the library inside a client account
                           (native edition); deterministic, idempotent (CREATE OR REPLACE)
"""

from __future__ import annotations

import json

from altitude.core.generated import stamp
from altitude.core.ids import canonical_json
from altitude.core.rubric import default_rubrics
from altitude.patterns.library import DIALECTS, default_library
from altitude.patterns.model import CHECKLIST, SEVERITY_ORDER

SOURCE = "knowledge/dialects/**, knowledge/rubrics/*.yaml"


def _cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ")


def _dialect_order() -> list[str]:
    lib = default_library()
    extra = sorted({i.source_dialect for i in lib.issues.values()} - set(DIALECTS))
    return list(DIALECTS) + extra


def known_issues_md() -> str:
    lib = default_library()
    by_sev = {s: sum(1 for i in lib.issues.values() if i.severity == s) for s in SEVERITY_ORDER}
    lines = ["# Known-issues catalogue", "",
             f"Pattern Library `{lib.version}` — {len(lib.issues)} issues "
             f"({', '.join(f'{k}: {v}' for k, v in by_sev.items())}). "
             "Severity: S1 silent wrong answers · S2 failure/rewrite · S3 performance/cost · S4 cosmetic/operational.",
             ""]
    for d in _dialect_order():
        issues = sorted((i for i in lib.issues.values() if i.source_dialect == d),
                        key=lambda i: (i.id))
        if not issues:
            continue
        lines += [f"## {d}", "", "| Id | Sev | Issue | Detector | Primary fix | Tests |", "|---|---|---|---|---|---|"]
        for i in issues:
            lines.append(f"| {i.id} | {i.severity} | {_cell(i.title)} | `{i.detection['detector']}` | "
                         f"{i.primary_fix.id} | {len(i.tests)} |")
        lines.append("")
        for i in issues:
            applies = f" Applies to: {', '.join(i.applies_to)}." if i.source_dialect == "common" else ""
            lines += [f"### {i.id} — {i.title}", "",
                      f"Severity **{i.severity}** · checklist items {', '.join(map(str, i.checklist_items)) or '—'}"
                      f" · decision required: {'yes' if i.decision_required else 'no'} · last verified "
                      f"{i.last_verified} by {i.verified_by}.{applies}", "",
                      "Symptoms:", ""]
            lines += [f"- {s}" for s in i.symptoms]
            det = i.detection
            lines += ["", f"Detection ({det['type']}): " + "; ".join(
                x for x in (det.get("static_rule"), det.get("profile_rule")) if x) +
                f". Detectors: {', '.join(f'`{x}`' for x in i.detectors)}.", "", "Fix patterns:", ""]
            lines += [f"- **{f.id}** — {f.description} *(when: {f.applies_when})*" for f in i.fix_patterns]
            lines += ["", f"Tests: {', '.join(i.tests)}. Validation normalisation: {i.validation_normalisation}", ""]
    return "\n".join(lines)


def mappings_md() -> str:
    lib = default_library()
    lines = ["# Conversion mappings", ""]
    for d in _dialect_order():
        rows = sorted((m for m in lib.mappings if m["source_dialect"] == d), key=lambda m: m["id"])
        if not rows:
            continue
        lines += [f"## {d}", "", "| Id | Category | Source | Snowflake | Note | Issues |", "|---|---|---|---|---|---|"]
        for m in rows:
            lines.append(f"| {m['id']} | {m['category']} | {_cell(m['source_construct'])} | "
                         f"{_cell(m['target_construct'])} | {_cell(m.get('note') or '')} | "
                         f"{', '.join(m.get('related_issues', [])) or '—'} |")
        lines.append("")
    return "\n".join(lines)


def drift_checklist_md() -> str:
    lib = default_library()
    lines = ["# Cross-source semantic-drift checklist (Section 10.13)", "",
             "Known issues with an executable detector per checklist item and source dialect. "
             "Run `altitude patterns scan --dialect <d> <files>` to check code against it.", "",
             "| # | Checklist item | " + " | ".join(DIALECTS) + " |", "|---|---|" + "---|" * len(DIALECTS)]
    for n, title in CHECKLIST.items():
        cells = []
        for d in DIALECTS:
            ids = sorted(i.id for i in lib.issues_for(d) if n in i.checklist_items)
            cells.append(", ".join(ids) or "—")
        lines.append(f"| {n} | {_cell(title)} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _s(v) -> str:
    if v is None:
        return "NULL"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def _arr(vals) -> str:
    return "ARRAY_CONSTRUCT(" + ", ".join(_s(v) for v in vals) + ")"


def _json(obj) -> str:
    return f"PARSE_JSON({_s(canonical_json(obj))})"


def pattern_library_sql() -> str:
    lib = default_library()
    rs = default_rubrics()
    out = [
        "-- Pattern Library for the native edition: run inside the client account (no data leaves it).",
        f"-- Pattern Library version {lib.version}; rubric set {rs.version}.",
        "CREATE SCHEMA IF NOT EXISTS KNOWLEDGE;",
        "CREATE OR REPLACE TABLE KNOWLEDGE.PATTERN (PATTERN_ID VARCHAR PRIMARY KEY, SOURCE_DIALECT VARCHAR NOT NULL, "
        "SOURCE_CONSTRUCT VARCHAR NOT NULL, TARGET_CONSTRUCT VARCHAR NOT NULL, NOTE VARCHAR, LAST_VERIFIED DATE NOT NULL);",
        "CREATE OR REPLACE TABLE KNOWLEDGE.KNOWN_ISSUE (ISSUE_ID VARCHAR PRIMARY KEY, SOURCE_DIALECT VARCHAR NOT NULL, "
        "APPLIES_TO ARRAY, TITLE VARCHAR NOT NULL, SEVERITY VARCHAR NOT NULL, CHECKLIST_ITEMS ARRAY, "
        "DETECTION_RULE VARCHAR NOT NULL, FIX_PATTERN_ID VARCHAR, TEST_CASE_IDS ARRAY, DECISION_REQUIRED BOOLEAN, "
        "LAST_VERIFIED DATE NOT NULL, VERIFIED_BY VARCHAR NOT NULL);",
        "CREATE OR REPLACE TABLE KNOWLEDGE.FIX_PATTERN (FIX_PATTERN_ID VARCHAR PRIMARY KEY, ISSUE_ID VARCHAR NOT NULL, "
        "DESCRIPTION VARCHAR NOT NULL, APPLIES_WHEN VARCHAR);",
        "CREATE OR REPLACE TABLE KNOWLEDGE.TEST_CASE (TEST_CASE_ID VARCHAR PRIMARY KEY, ISSUE_ID VARCHAR, "
        "KIND VARCHAR, DESCRIPTION VARCHAR NOT NULL, DEFINITION VARIANT NOT NULL);",
        "CREATE OR REPLACE TABLE KNOWLEDGE.RUBRIC_VERSION (NAMESPACE VARCHAR NOT NULL, VERSION VARCHAR NOT NULL, "
        "RUBRIC_SET_VERSION VARCHAR NOT NULL, \"VALUES\" VARIANT NOT NULL, PRIMARY KEY (NAMESPACE, VERSION));",
        "",
    ]
    for m in sorted(lib.mappings, key=lambda m: m["id"]):
        out.append("INSERT INTO KNOWLEDGE.PATTERN VALUES (" + ", ".join([
            _s(m["id"]), _s(m["source_dialect"]), _s(m["source_construct"]), _s(m["target_construct"]),
            _s(m.get("note") or None), f"DATE {_s(m['last_verified'])}"]) + ");")
    out.append("")
    for i in sorted(lib.issues.values(), key=lambda i: i.id):
        out.append("INSERT INTO KNOWLEDGE.KNOWN_ISSUE SELECT " + ", ".join([
            _s(i.id), _s(i.source_dialect), _arr(i.applies_to), _s(i.title), _s(i.severity),
            _arr(i.checklist_items), _s(i.detection["detector"]), _s(i.primary_fix.id), _arr(i.tests),
            "TRUE" if i.decision_required else "FALSE", f"DATE {_s(i.last_verified)}", _s(i.verified_by)]) + ";")
        for f in i.fix_patterns:
            out.append("INSERT INTO KNOWLEDGE.FIX_PATTERN VALUES (" + ", ".join([
                _s(f.id), _s(i.id), _s(f.description), _s(f.applies_when)]) + ");")
    out.append("")
    for tid, tc in sorted(lib.tests.items()):
        definition = {k: v for k, v in tc.items() if not k.startswith("_")}
        out.append("INSERT INTO KNOWLEDGE.TEST_CASE SELECT " + ", ".join([
            _s(tid), _s(tc["issue_id"]), _s(tc["kind"]), _s(tc["description"]),
            _json(json.loads(json.dumps(definition, default=str)))]) + ";")
    out.append("")
    for ns in sorted(rs.namespaces):
        out.append("INSERT INTO KNOWLEDGE.RUBRIC_VERSION SELECT " + ", ".join([
            _s(ns), _s(rs.versions[ns]), _s(rs.version), _json(rs.namespaces[ns])]) + ";")
    return "\n".join(out) + "\n"


def generate() -> dict[str, str]:
    return {
        "knowledge_publish/known_issues.md": stamp(known_issues_md(), ".md", SOURCE),
        "knowledge_publish/mappings.md": stamp(mappings_md(), ".md", "knowledge/dialects/*/mappings.yaml"),
        "knowledge_publish/drift_checklist.md": stamp(drift_checklist_md(), ".md", "knowledge/dialects/*/known_issues.yaml"),
        "knowledge_publish/pattern_library.sql": stamp(pattern_library_sql(), ".sql", SOURCE),
    }
