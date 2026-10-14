"""Golden-test runner for the Pattern Library (Section 16: golden-test corpus per dialect).

A golden test proves, on synthetic data, that

1. the drift checker detects the issue in the *source* code;
2. the DuckDB emulation of the source semantics yields ``expected_rows``;
3. the naive Snowflake conversion diverges from it (or errors, when ``expect: error``);
4. the Snowflake code with the fix pattern applied reproduces ``expected_rows``.

Snowflake SQL is validated with sqlglot's Snowflake parser and executed by transpiling to
DuckDB with ``unsupported_level=RAISE`` (no silently dropped arguments). Where DuckDB cannot
express a Snowflake behaviour (e.g. TO_DATE on integer strings = epoch seconds) the test
supplies an explicit ``duckdb`` emulation next to the ``snowflake`` text.

Detector tests assert hits (``expect_issues``), non-hits (``expect_absent``) and exact lines
(``expect_lines``); profile tests do the same for profile detectors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import duckdb
import sqlglot
from sqlglot.errors import ErrorLevel

from .library import PatternLibrary, default_library, normalise_dialect
from .scan import Scanner


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""


@dataclass
class CaseResult:
    test_id: str
    issue_id: str
    kind: str
    checks: list[Check] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.ok for c in self.checks)

    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.ok]


def norm_cell(v: Any) -> Any:
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    if isinstance(v, datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, date):
        return v.isoformat()
    return v


def norm_rows(rows) -> list[tuple]:
    return [tuple(norm_cell(c) for c in r) for r in rows]


def to_duckdb(snowflake_sql: str) -> list[str]:
    return [s for s in sqlglot.transpile(snowflake_sql, read="snowflake", write="duckdb",
                                         unsupported_level=ErrorLevel.RAISE) if s.strip()]


def execute(fixture: str, statements: list[str] | str) -> list[tuple]:
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'UTC'")
        con.execute(fixture)
        if isinstance(statements, str):
            statements = [statements]
        cur = None
        for st in statements:
            cur = con.execute(st)
        return norm_rows(cur.fetchall() if cur is not None and cur.description else [])
    finally:
        con.close()


def _conversion_rows(fixture: str, conv: dict) -> list[tuple]:
    return execute(fixture, conv["duckdb"] if conv.get("duckdb") else to_duckdb(conv["snowflake"]))


def _check_hits(res: CaseResult, hits, tc: dict) -> None:
    found = {h.issue_id for h in hits}
    for iid in tc.get("expect_issues", []):
        res.checks.append(Check(f"detects {iid}", iid in found, f"hits: {sorted(found)}"))
    for iid in tc.get("expect_absent", []):
        res.checks.append(Check(f"does not flag {iid}", iid not in found,
                                f"unexpected: {[(h.line, h.snippet) for h in hits if h.issue_id == iid]}"))
    for iid, lines in (tc.get("expect_lines") or {}).items():
        got = sorted({h.line for h in hits if h.issue_id == iid})
        res.checks.append(Check(f"{iid} lines", got == sorted(lines), f"expected {sorted(lines)}, got {got}"))


def run_case(tc: dict, library: PatternLibrary | None = None, scanner: Scanner | None = None) -> CaseResult:
    library = library or default_library()
    scanner = scanner or Scanner(library=library, strict=True)
    res = CaseResult(tc["id"], tc["issue_id"], tc["kind"])
    dialect = library.scan_dialect_of(tc)

    if tc["kind"] == "profile":
        _check_hits(res, scanner.scan_profile(tc["profile"], dialect), tc)
        return res

    hits = scanner.scan_sql(tc["source_sql"], dialect)
    if tc["kind"] == "detector":
        _check_hits(res, hits, tc)
        return res

    # ---------------------------------------------------------------- golden
    res.checks.append(Check(f"detector flags {tc['issue_id']} in source", tc["issue_id"] in {h.issue_id for h in hits},
                            f"hits: {sorted({h.issue_id for h in hits})}"))
    _check_hits(res, hits, tc)
    try:
        library.fix_pattern(tc["fix_pattern"])
        res.checks.append(Check("fix pattern exists", True))
    except KeyError:
        res.checks.append(Check("fix pattern exists", False, tc["fix_pattern"]))
    expected = norm_rows(tc["expected_rows"])
    for label in ("naive", "fixed"):
        try:
            sqlglot.parse(tc[label]["snowflake"], read="snowflake", error_level=ErrorLevel.RAISE)
            res.checks.append(Check(f"{label} is valid Snowflake SQL", True))
        except sqlglot.errors.SqlglotError as e:
            res.checks.append(Check(f"{label} is valid Snowflake SQL", False, str(e).splitlines()[0]))
    try:
        got = execute(tc["fixture"], tc["source_emulation"])
        res.checks.append(Check("source emulation yields expected rows", got == expected, f"got {got}, expected {expected}"))
    except duckdb.Error as e:
        res.checks.append(Check("source emulation yields expected rows", False, f"error: {e}"))

    expect = tc["naive"].get("expect", "diverge")
    try:
        got = _conversion_rows(tc["fixture"], tc["naive"])
        ok = expect == "diverge" and got != expected
        res.checks.append(Check("naive conversion diverges", ok, f"naive rows {got} (expected to differ)"))
    except (duckdb.Error, sqlglot.errors.SqlglotError) as e:
        res.checks.append(Check("naive conversion diverges", True, f"naive conversion errors: {e}"))
    try:
        got = _conversion_rows(tc["fixture"], tc["fixed"])
        res.checks.append(Check("fixed conversion converges", got == expected, f"got {got}, expected {expected}"))
    except (duckdb.Error, sqlglot.errors.SqlglotError) as e:
        res.checks.append(Check("fixed conversion converges", False, f"error: {e}"))
    return res


def run_all(library: PatternLibrary | None = None, dialect: str | None = None, ids: list[str] | None = None,
            kinds: tuple[str, ...] = ("golden", "detector", "profile")) -> list[CaseResult]:
    library = library or default_library()
    scanner = Scanner(library=library, strict=True)
    want = normalise_dialect(dialect) if dialect else None
    out = []
    for tid, tc in sorted(library.tests.items()):
        if ids and tid not in ids:
            continue
        if tc["kind"] not in kinds:
            continue
        if want and want not in library.issue(tc["issue_id"]).applies_to:
            continue
        out.append(run_case(tc, library, scanner))
    return out


def coverage_problems(library: PatternLibrary | None = None) -> list[str]:
    """Structural M1 acceptance: every issue has a registered detector and listed tests; every S1 issue
    has at least one golden test; test/issue cross-references agree."""
    from .detectors import REGISTRY, ensure_loaded

    ensure_loaded()
    library = library or default_library()
    problems: list[str] = []
    for issue in library.issues.values():
        for det in issue.detectors:
            if det not in REGISTRY:
                problems.append(f"{issue.id}: detector {det} is not registered")
        if issue.detection["detector"] in REGISTRY and REGISTRY[issue.detection["detector"]].kind != \
                issue.detection["detector"].split(".")[0]:
            problems.append(f"{issue.id}: detector kind mismatch")
        for tid in issue.tests:
            tc = library.tests.get(tid)
            if tc is None:
                problems.append(f"{issue.id}: test {tid} does not exist")
            elif tc["issue_id"] != issue.id:
                problems.append(f"{issue.id}: test {tid} belongs to {tc['issue_id']}")
        if issue.severity == "S1":
            goldens = [t for t in library.tests_for(issue.id) if t["kind"] == "golden"]
            if not goldens:
                problems.append(f"{issue.id}: S1 issue has no golden test")
            static = [d for d in issue.detectors if d.startswith("static.")]
            if not static:
                problems.append(f"{issue.id}: S1 issue has no static (executable) detector")
    for tid, tc in library.tests.items():
        issue = library.issues.get(tc["issue_id"])
        if issue is None:
            problems.append(f"{tid}: unknown issue {tc['issue_id']}")
        elif tid not in issue.tests:
            problems.append(f"{tid}: not listed in {issue.id}.tests")
    return sorted(problems)
