"""SnowConvert AI CLI integration.

``SnowConvertCLI`` discovers the binary (explicit path > ``ALTITUDE_SNOWCONVERT_BIN`` > ``PATH`` names from
``knowledge/conversion/snowconvert.yaml``), detects its version, invokes it per source dialect and parses
its reports:

- ``Issues*.csv``            one row per EWI / FDM / PRF / OOS (code, severity, file, line, message ...)
- ``TopLevelCodeUnits*.csv`` assessment: per code unit LOC, EWI/FDM/PRF counts, conversion status

Report headers differ between CLI versions; columns are resolved through alias lists held as data.
Converted output files are matched back to their source files, and each issue is located in the
converted output by its marker (``!!!RESOLVE EWI!!! /*** CODE - ... ***/!!!`` or ``--** CODE - ... **``).
"""

from __future__ import annotations

import csv
import io
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable, Sequence

from altitude.core.errors import AltitudeError

from . import kb
from .models import ConversionOutput, ConvertedFile, Issue


class SnowConvertError(AltitudeError):
    """The SnowConvert AI CLI failed or produced unusable output."""


# --------------------------------------------------------------------------- report parsing


def _read_csv(text: str) -> list[dict[str, str]]:
    text = text.lstrip("﻿")
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = []
    for row in reader:
        if row is None or not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue
        rows.append({(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in row.items()})
    return rows


def _resolver(headers: Iterable[str], aliases: dict[str, list[str]]) -> dict[str, str]:
    norm = {re.sub(r"[^a-z0-9]", "", h.lower()): h for h in headers}
    out: dict[str, str] = {}
    for field, names in aliases.items():
        for name in names:
            key = re.sub(r"[^a-z0-9]", "", name.lower())
            if key in norm:
                out[field] = norm[key]
                break
    return out


def _int(value: str | None) -> int | None:
    if value is None:
        return None
    m = re.search(r"-?\d+", value.replace(",", ""))
    return int(m.group(0)) if m else None


def _rel(path: str) -> str:
    p = path.replace("\\", "/").strip()
    p = re.sub(r"^[A-Za-z]:/", "", p)
    while p.startswith("./"):
        p = p[2:]
    return p.lstrip("/")


def parse_issues_csv(text: str, cfg: dict | None = None) -> list[Issue]:
    """Parse a SnowConvert ``Issues.csv`` report into :class:`Issue` records."""
    cfg = cfg or kb.snowconvert_config()
    rows = _read_csv(text)
    if not rows:
        return []
    cols = _resolver(rows[0].keys(), cfg["issue_columns"])
    missing = [f for f in ("code", "file") if f not in cols]
    if missing:
        raise SnowConvertError(f"issues report lacks required column(s): {', '.join(missing)}")
    issues = []
    for row in rows:
        code = row.get(cols["code"], "").strip()
        if not code:
            continue
        tool_sev = row.get(cols.get("severity", ""), "") or None
        category, severity = kb.severity_for(code, tool_sev, cfg)
        message = row.get(cols.get("message", ""), "") or row.get(cols.get("name", ""), "") or code
        name = row.get(cols.get("name", ""), "")
        if name and name not in message:
            message = f"{name}: {message}"
        issues.append(Issue(
            code=code.upper(),
            category=category,
            severity=severity,
            message=" ".join(message.split()),
            file=_rel(row.get(cols["file"], "")),
            source_line=_int(row.get(cols.get("line", ""))),
            column=_int(row.get(cols.get("column", ""))),
            snippet=row.get(cols.get("snippet", "")) or None,
            tool_severity=tool_sev,
        ))
    return issues


def parse_assessment_csv(text: str, cfg: dict | None = None) -> list[dict[str, Any]]:
    """Parse a ``TopLevelCodeUnits.csv`` assessment report."""
    cfg = cfg or kb.snowconvert_config()
    rows = _read_csv(text)
    if not rows:
        return []
    cols = _resolver(rows[0].keys(), cfg.get("assessment_columns", {}))
    out = []
    ints = {"lines_of_code", "ewi_count", "fdm_count", "prf_count"}
    for n, row in enumerate(rows, 1):
        rec: dict[str, Any] = {}
        for field, header in cols.items():
            value = row.get(header, "")
            rec[field] = _int(value) if field in ints else (value or None)
        if rec.get("file_name"):
            rec["file_name"] = _rel(rec["file_name"])
        rec.setdefault("code_unit_id", None)
        rec["code_unit_id"] = rec["code_unit_id"] or f"CU-{n:05d}"
        out.append(rec)
    return out


_MARKER = re.compile(r"(!!!RESOLVE EWI!!!|--\s*\*\*|/\*\*\*)")


def locate_markers(output_text: str, issues: list[Issue]) -> None:
    """Set ``issue.line`` to the converted-output line of the issue's marker (k-th issue <-> k-th marker)."""
    lines = output_text.splitlines()
    by_code: dict[str, list[int]] = {}
    for idx, line in enumerate(lines, 1):
        if not _MARKER.search(line):
            continue
        for code in re.findall(r"\b((?:SSC|MSC|ALT)-?[A-Z]{2,3}-?[A-Z]{0,2}\d{3,5})\b", line):
            by_code.setdefault(code.upper(), []).append(idx)
    seen: dict[str, int] = {}
    for issue in sorted(issues, key=lambda i: (i.source_line or 0, i.column or 0)):
        if issue.line is not None:
            continue
        k = seen.get(issue.code, 0)
        found = by_code.get(issue.code, [])
        if k < len(found):
            issue.line = found[k]
        seen[issue.code] = k + 1


# --------------------------------------------------------------------------- CLI wrapper


class SnowConvertCLI:
    """Subprocess wrapper around the SnowConvert AI CLI."""

    name = "snowconvert"

    def __init__(self, binary: str | Sequence[str] | None = None, cfg: dict | None = None,
                 env: dict[str, str] | None = None):
        self.cfg = cfg or kb.snowconvert_config()
        self.env = env if env is not None else dict(os.environ)
        self.command = self._resolve(binary)
        self._version: str | None = None

    def _resolve(self, binary: str | Sequence[str] | None) -> list[str] | None:
        if binary is None:
            binary = self.env.get(self.cfg["binary"]["env_var"]) or None
        if binary is None:
            for name in self.cfg["binary"]["names"]:
                found = shutil.which(name, path=self.env.get("PATH"))
                if found:
                    return [found]
            return None
        cmd = shlex.split(binary) if isinstance(binary, str) else list(binary)
        if not cmd:
            return None
        exe = cmd[0]
        if os.sep in exe or "/" in exe:
            if not Path(exe).exists():
                return None
        elif not shutil.which(exe, path=self.env.get("PATH")):
            return None
        return cmd

    @property
    def available(self) -> bool:
        return self.command is not None

    def version(self) -> str:
        if self._version is None:
            if not self.available:
                raise SnowConvertError("SnowConvert AI CLI is not installed")
            proc = subprocess.run(self.command + list(self.cfg["binary"]["version_args"]), capture_output=True,
                                  text=True, env=self.env, timeout=self.cfg["binary"].get("timeout_seconds"))
            m = re.search(self.cfg["binary"]["version_pattern"], (proc.stdout or "") + (proc.stderr or ""))
            if proc.returncode != 0 or not m:
                raise SnowConvertError(f"could not detect SnowConvert version (exit {proc.returncode})")
            self._version = m.group(1)
        return self._version

    def invocation(self, dialect: str, input_dir: Path, output_dir: Path) -> list[str]:
        d = self.cfg["dialects"].get(dialect)
        if d is None:
            raise SnowConvertError(f"SnowConvert does not support dialect {dialect!r}")
        args = [a.format(command=d["command"], input=str(input_dir), output=str(output_dir))
                for a in self.cfg["invocation"]]
        return list(self.command or []) + args

    def convert(self, input_dir: Path, dialect: str, output_dir: Path) -> ConversionOutput:
        if not self.available:
            raise SnowConvertError("SnowConvert AI CLI is not installed")
        input_dir, output_dir = Path(input_dir), Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        version = self.version()
        proc = subprocess.run(self.invocation(dialect, input_dir, output_dir), capture_output=True, text=True,
                              env=self.env, timeout=self.cfg["binary"].get("timeout_seconds"))
        if proc.returncode != 0:
            raise SnowConvertError(f"SnowConvert exited {proc.returncode}: {(proc.stderr or proc.stdout)[-2000:]}")
        return self.collect(input_dir, dialect, output_dir, version, log=proc.stdout)

    def collect(self, input_dir: Path, dialect: str, output_dir: Path, version: str, log: str = "") -> ConversionOutput:
        """Read converted files and reports from a SnowConvert output directory."""
        out_root = next((output_dir / d for d in self.cfg["output_dirs"] if (output_dir / d).is_dir()), output_dir)
        issues: list[Issue] = []
        for pattern in self.cfg["reports"]["issues"]:
            files = sorted(output_dir.glob(pattern))
            if files:
                issues = parse_issues_csv(files[-1].read_text(encoding="utf-8-sig"), self.cfg)
                break
        assessment: list[dict] = []
        for pattern in self.cfg["reports"].get("assessment", []):
            files = sorted(output_dir.glob(pattern))
            if files:
                assessment = parse_assessment_csv(files[-1].read_text(encoding="utf-8-sig"), self.cfg)
                break
        exts = set(self.cfg["dialects"][dialect]["extensions"])
        result = ConversionOutput(tool=self.name, tool_version=version, dialect=dialect, assessment=assessment, log=log)
        by_file: dict[str, list[Issue]] = {}
        for issue in issues:
            by_file.setdefault(issue.file, []).append(issue)
        for src in sorted(p for p in input_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts):
            rel = src.relative_to(input_dir).as_posix()
            converted = out_root / rel
            if not converted.exists():
                candidates = sorted(out_root.rglob(src.stem + ".*"))
                converted = candidates[0] if candidates else None
            output_text = converted.read_text() if converted else ""
            file_issues = _issues_for(rel, by_file)
            locate_markers(output_text, file_issues)
            result.files.append(ConvertedFile(rel, src.read_text(), output_text, file_issues))
        return result


def _issues_for(rel: str, by_file: dict[str, list[Issue]]) -> list[Issue]:
    out = list(by_file.get(rel, []))
    for name, items in by_file.items():
        if name != rel and (name.endswith("/" + rel) or rel.endswith("/" + name) or Path(name).name == rel):
            out.extend(items)
    for i in out:
        i.file = rel
    return out
