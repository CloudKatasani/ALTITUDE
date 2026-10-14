"""sqlglot fallback converter (teradata / oracle / tsql -> snowflake).

Used when the SnowConvert AI CLI is not installed. Every statement is transpiled with sqlglot; constructs
it cannot convert are reported as conversion issues with their own codes (``ALT-EWI-*`` / ``ALT-FDM-*``),
driven by the detectors in ``knowledge/conversion/fallback_rules.yaml`` (BTEQ dot-commands, cursors,
``@@ROWCOUNT``, packages, triggers, ...) plus generic parse / unsupported-construct issues.

The output mirrors SnowConvert conventions: each issue gets a marker line
``-- !!!RESOLVE EWI!!! /*** CODE - message ***/!!!`` directly above the affected statement, so the
remediation agent and reviewers find it the same way for either tool.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import sqlglot
from sqlglot import exp
from sqlglot.errors import ErrorLevel, ParseError, UnsupportedError

from . import kb
from .models import ConversionOutput, ConvertedFile, Issue
from .splitter import Unit, split_statements

DIALECT_ALIASES = {"sqlserver": "tsql", "mssql": "tsql", "sql-server": "tsql", "td": "teradata", "ora": "oracle"}
DEFAULT_EXTENSIONS = {
    "teradata": {".sql", ".bteq", ".btq", ".ddl", ".spl"},
    "oracle": {".sql", ".pks", ".pkb", ".prc", ".fnc", ".trg"},
    "tsql": {".sql"},
}
_ACTION_RANK = {"flag": 0, "keep": 1, "comment_out": 2}


def normalise_dialect(dialect: str) -> str:
    d = dialect.lower()
    return DIALECT_ALIASES.get(d, d)


def marker(code: str, message: str) -> str:
    return f"-- !!!RESOLVE EWI!!! /*** {code} - {message} ***/!!!"


@contextmanager
def _quiet_sqlglot() -> Iterator[None]:
    log = logging.getLogger("sqlglot")
    old = log.level
    log.setLevel(logging.ERROR)
    try:
        yield
    finally:
        log.setLevel(old)


class SqlglotConverter:
    """Offline converter built on sqlglot with knowledge-driven issue detectors."""

    name = "sqlglot"

    def __init__(self, rules: dict | None = None):
        self.rules = rules or kb.fallback_rules()
        self.generic = {g["code"]: g for g in self.rules["generic"]}
        self._codes = {
            "unrecognised": "ALT-EWI-0001",
            "unsupported": "ALT-EWI-0002",
            "parse": "ALT-EWI-0003",
        }

    @property
    def version(self) -> str:
        return f"sqlglot-{sqlglot.__version__}"

    # ------------------------------------------------------------------ public API
    def convert(self, input_dir: Path, dialect: str, output_dir: Path | None = None) -> ConversionOutput:
        dialect = normalise_dialect(dialect)
        input_dir = Path(input_dir)
        exts = DEFAULT_EXTENSIONS.get(dialect, {".sql"})
        result = ConversionOutput(tool=self.name, tool_version=self.version, dialect=dialect)
        for src in sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts):
            rel = src.relative_to(input_dir).as_posix()
            cf = self.convert_text(src.read_text(), dialect, rel)
            result.files.append(cf)
            if output_dir is not None:
                target = Path(output_dir) / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(cf.output_text)
        return result

    def convert_text(self, text: str, dialect: str, rel: str = "input.sql") -> ConvertedFile:
        dialect = normalise_dialect(dialect)
        rules = [r for r in self.rules["rules"] if dialect in r["dialects"]]
        blocks: list[str] = []
        issues: list[Issue] = []
        start = 1
        for unit in split_statements(text, dialect):
            block_lines, unit_issues = self._convert_unit(unit, dialect, rules, rel)
            for issue in unit_issues:
                issue.region_end = start + len(block_lines) - 1
            start += len(block_lines) + 1  # blocks are separated by one blank line
            issues.extend(unit_issues)
            blocks.append("\n".join(block_lines))
        output = "\n\n".join(blocks).rstrip() + "\n" if blocks else ""
        _relocate(output, issues)
        return ConvertedFile(rel, text, output, issues)

    # ------------------------------------------------------------------ internals
    def _issue(self, code: str, severity: str, message: str, rel: str, src_line: int, snippet: str,
               detector: str | None = None, known: str | None = None) -> Issue:
        category = "FDM" if "-FDM-" in code else ("PRF" if "-PRF-" in code else "EWI")
        return Issue(code=code, category=category, severity=severity, message=message, file=rel,
                     source_line=src_line, snippet=snippet.strip()[:200], tool_severity=severity,
                     known_issue=known, detector_id=detector)

    def _generic(self, key: str, rel: str, src_line: int, snippet: str, detail: str = "") -> Issue:
        g = self.generic[self._codes[key]]
        msg = g["message"].format(detail=" ".join(detail.split())[:160])
        return self._issue(g["code"], g["severity"], msg, rel, src_line, snippet, g["id"])

    def _convert_unit(self, unit: Unit, dialect: str, rules: list[dict], rel: str
                      ) -> tuple[list[str], list[Issue]]:
        code = unit.code.rstrip()
        prefix = unit.text.lstrip()[: len(unit.text.lstrip()) - len(unit.code)].rstrip()
        first_code_line = unit.start_line + prefix.count("\n") + (1 if prefix else 0)
        if unit.kind == "comment":
            return unit.text.strip("\n").splitlines(), []

        issues: list[Issue] = []
        action = None
        seen: set[tuple[str, str]] = set()
        for rule in rules:
            for m in re.finditer(rule["pattern"], code, re.I | re.M):
                key = (rule["id"], m.group(0).strip().upper())
                if key in seen:
                    continue
                seen.add(key)
                src_line = first_code_line + code[: m.start()].count("\n")
                line_text = code.splitlines()[code[: m.start()].count("\n")] if code else ""
                issues.append(self._issue(rule["code"], rule["severity"],
                                          rule["message"].format(match=m.group(0).strip()), rel, src_line,
                                          line_text, rule["id"], rule.get("known_issue")))
                if action is None or _ACTION_RANK[rule["action"]] > _ACTION_RANK[action]:
                    action = rule["action"]
                if rule["id"] in {"FB-TD-01", "FB-TD-02", "FB-TD-03"}:
                    break

        if unit.kind == "dot" and action is None:
            issues.append(self._generic("parse", rel, first_code_line, code, "unrecognised BTEQ dot-command"))
            action = "comment_out"

        if action == "comment_out":
            body = ["-- " + ln for ln in code.splitlines()]
        elif action == "keep":
            body = code.splitlines()
        else:
            body_text, extra = self._transpile(code, dialect, rel, first_code_line, flagged=bool(issues))
            issues.extend(extra)
            body = body_text.splitlines()

        lines = prefix.splitlines() if prefix else []
        lines.extend(marker(issue.code, issue.message) for issue in issues)
        lines.extend(body)
        return lines, issues

    def _transpile(self, code: str, dialect: str, rel: str, line: int, flagged: bool) -> tuple[str, list[Issue]]:
        issues: list[Issue] = []
        with _quiet_sqlglot():
            try:
                expressions = sqlglot.parse(code, read=dialect)
            except (ParseError, sqlglot.errors.TokenError) as e:
                issues.append(self._generic("parse", rel, line, code, str(e).splitlines()[0]))
                return "\n".join("-- " + ln for ln in code.splitlines()), issues
            pieces: list[str] = []
            for expression in expressions:
                if expression is None:
                    continue
                if isinstance(expression, exp.Command):
                    if not flagged:
                        issues.append(self._generic("unrecognised", rel, line, code))
                    pieces.append(expression.sql(dialect="snowflake"))
                    continue
                try:
                    pieces.append(expression.sql(dialect="snowflake", pretty=True,
                                                 unsupported_level=ErrorLevel.RAISE))
                except UnsupportedError as e:
                    issues.append(self._generic("unsupported", rel, line, code, str(e).splitlines()[0]))
                    pieces.append(code.rstrip().rstrip(";"))
        return ";\n".join(pieces) + ";", issues


def _relocate(output: str, issues: list[Issue]) -> None:
    """Point each issue at the exact output line holding its marker (in emission order)."""
    lines = output.splitlines()
    cursor = 0
    for issue in issues:
        needle = f"/*** {issue.code} - "
        for idx in range(cursor, len(lines)):
            if needle in lines[idx] and "!!!RESOLVE EWI!!!" in lines[idx]:
                issue.line = idx + 1
                cursor = idx + 1
                break
