"""Structural linter for generated Terraform (terraform itself is not required).

Checks, with precise ``file:line`` messages:

- strings are closed and ``{}``/``[]``/``()`` are balanced outside strings;
- resource addresses are unique and every ``snowflake_*.<name>`` / ``var.<name>`` reference is defined;
- no object privileges are granted to users (only ``*_to_account_role`` privilege grants exist) and users
  only receive functional/agent roles, never access roles;
- every warehouse references a defined resource monitor, auto-resumes, and its ``auto_suspend`` and
  statement timeout are within the compute rubric; every resource monitor suspends within the rubric;
- databases follow the landing-zone naming regex (platform databases excepted).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from altitude.core.rubric import RubricSet, default_rubrics

RES_RE = re.compile(r'^resource\s+"([a-z0-9_]+)"\s+"([a-z0-9_]+)"\s*\{\s*$')
VAR_RE = re.compile(r'^variable\s+"([a-z0-9_]+)"\s*\{\s*$')
REF_RE = re.compile(r"\b(snowflake_[a-z_]+)\.([a-z0-9_]+)\b")
VARREF_RE = re.compile(r"\bvar\.([a-z0-9_]+)\b")
ATTR_RE = re.compile(r"^\s*([a-z_]+)\s*=\s*(.+?)\s*$")
PAIRS = {"}": "{", "]": "[", ")": "("}


@dataclass
class Resource:
    rtype: str
    name: str
    file: str
    line: int
    attrs: dict[str, str] = field(default_factory=dict)

    @property
    def address(self) -> str:
        return f"{self.rtype}.{self.name}"

    def str_attr(self, key: str) -> str | None:
        v = self.attrs.get(key)
        return v[1:-1] if v and v.startswith('"') and v.endswith('"') else None


def _strip_strings(line: str) -> tuple[str, bool]:
    """Return ``line`` with string contents blanked and whether a string is left open."""
    out, in_str, esc = [], False, False
    for ch in line:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                out.append('"')
            continue
        if ch == '"':
            in_str = True
            out.append('"')
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out), in_str


def parse(files: dict[str, str]) -> tuple[list[Resource], set[str], list[str], list[tuple[str, int, str]]]:
    """Return resources, variables, structural problems and (file, line, code) for every code line."""
    resources: list[Resource] = []
    variables: set[str] = set()
    problems: list[str] = []
    code_lines: list[tuple[str, int, str]] = []
    for fname, text in sorted(files.items()):
        stack: list[tuple[str, int]] = []
        current: Resource | None = None
        for i, raw in enumerate(text.splitlines(), 1):
            code, open_str = _strip_strings(raw)
            if open_str:
                problems.append(f"{fname}:{i}: unterminated string")
            code_lines.append((fname, i, code))
            if not stack:
                m = RES_RE.match(raw.strip())
                if m:
                    current = Resource(m.group(1), m.group(2), fname, i)
                    resources.append(current)
                v = VAR_RE.match(raw.strip())
                if v:
                    variables.add(v.group(1))
            elif len(stack) == 1 and current is not None:
                a = ATTR_RE.match(raw)
                if a:
                    current.attrs[a.group(1)] = a.group(2)
            for ch in code:
                if ch in "{[(":
                    stack.append((ch, i))
                elif ch in "}])":
                    if not stack or stack[-1][0] != PAIRS[ch]:
                        problems.append(f"{fname}:{i}: unbalanced '{ch}'")
                    else:
                        stack.pop()
            if not stack:
                current = None
        for ch, line in stack:
            problems.append(f"{fname}:{line}: '{ch}' is never closed")
    return resources, variables, problems, code_lines


def lint(files: dict[str, str], rubrics: RubricSet | None = None, database_regex: str | None = None,
         platform_databases: tuple[str, ...] = ("GOVERNANCE",)) -> list[str]:
    rubrics = rubrics or default_rubrics()
    resources, variables, problems, code_lines = parse(files)
    by_addr: dict[str, Resource] = {}
    for r in resources:
        if r.address in by_addr:
            problems.append(f"{r.file}:{r.line}: duplicate resource {r.address} "
                            f"(first defined at {by_addr[r.address].file}:{by_addr[r.address].line})")
        by_addr.setdefault(r.address, r)
    for fname, i, code in code_lines:
        if RES_RE.match(code.strip()):
            continue
        for rtype, name in REF_RE.findall(code):
            if f"{rtype}.{name}" not in by_addr:
                problems.append(f"{fname}:{i}: reference to undefined resource {rtype}.{name}")
        for name in VARREF_RE.findall(code):
            if name not in variables:
                problems.append(f"{fname}:{i}: reference to undefined variable var.{name}")

    def target(expr: str | None) -> Resource | None:
        m = REF_RE.search(expr or "")
        return by_addr.get(f"{m.group(1)}.{m.group(2)}") if m else None

    max_suspend = rubrics.get("rubric.compute.auto_suspend_max_seconds")
    max_timeout = rubrics.get("rubric.compute.statement_timeout_max_seconds")
    max_pct = rubrics.get("rubric.foundation.monitor_suspend_at_max_pct")
    min_notify = rubrics.get("rubric.foundation.monitor_notify_min_triggers")
    regex = re.compile(database_regex) if database_regex else None
    for r in resources:
        where = f"{r.file}:{r.line}: {r.address}"
        if r.rtype.startswith("snowflake_grant_privileges_to_") and r.rtype not in (
                "snowflake_grant_privileges_to_account_role", "snowflake_grant_privileges_to_database_role"):
            problems.append(f"{where}: object privileges may only be granted to roles, never to users")
        if r.rtype == "snowflake_grant_account_role" and "user_name" in r.attrs:
            role = target(r.attrs.get("role_name"))
            role_name = role.str_attr("name") if role else r.str_attr("role_name")
            if role_name is None or role_name.startswith("AR_"):
                problems.append(f"{where}: users may only receive functional or agent roles, not access role "
                                f"{role_name!r}")
        if r.rtype == "snowflake_warehouse":
            mon = target(r.attrs.get("resource_monitor"))
            if mon is None or mon.rtype != "snowflake_resource_monitor":
                problems.append(f"{where}: warehouse has no resource monitor")
            try:
                suspend = int(r.attrs.get("auto_suspend", ""))
            except ValueError:
                suspend = None
            if suspend is None or suspend > max_suspend or suspend < 1:
                problems.append(f"{where}: auto_suspend {r.attrs.get('auto_suspend')} outside 1..{max_suspend}s "
                                "(rubric.compute.auto_suspend_max_seconds)")
            if r.attrs.get("auto_resume") != '"true"':
                problems.append(f"{where}: auto_resume must be \"true\"")
            try:
                timeout = int(r.attrs.get("statement_timeout_in_seconds", ""))
            except ValueError:
                timeout = None
            if timeout is None or timeout > max_timeout:
                problems.append(f"{where}: statement timeout must be set and <= {max_timeout}s")
        if r.rtype == "snowflake_resource_monitor":
            try:
                pct = int(r.attrs.get("suspend_trigger", ""))
            except ValueError:
                pct = None
            if pct is None or pct > max_pct:
                problems.append(f"{where}: resource monitor must suspend at <= {max_pct}%")
            notify = r.attrs.get("notify_triggers", "[]").strip("[]")
            if len([x for x in notify.split(",") if x.strip()]) < min_notify:
                problems.append(f"{where}: resource monitor needs at least {min_notify} notify trigger(s)")
        if r.rtype == "snowflake_database" and regex:
            name = r.str_attr("name")
            if name and name not in platform_databases and not regex.match(name):
                problems.append(f"{where}: database {name} does not follow the naming convention {database_regex}")
    return problems
