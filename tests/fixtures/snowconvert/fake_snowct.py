#!/usr/bin/env python3
"""Test double for the SnowConvert AI CLI (``snowct``).

Mimics the CLI surface the wrapper relies on: ``--version`` and ``<dialect> -i <input> -o <output>``.
It copies each source file to ``<output>/Output/SnowConvert/<rel>`` inserting SnowConvert-style markers,
and writes ``Reports/SnowConvert/Issues.<ts>.csv`` and ``TopLevelCodeUnits.<ts>.csv``.
"""

import csv
import sys
from pathlib import Path

VERSION = "SnowConvert AI CLI 2.7.3 (build 20260930)"
RULES = [
    # (substring, code, severity, name, marker style)
    ("QUALIFY", "SSC-EWI-0073", "Medium", "Pending Functional Equivalence Review", "ewi"),
    ("CREATE SET TABLE", "SSC-FDM-TD0024", "Low", "Set table functionality not supported", "fdm"),
    (".GOTO", "SSC-EWI-0001", "Critical", "Unrecognized token on the line of the source code", "ewi"),
]
EXTENSIONS = {".sql", ".bteq", ".btq", ".ddl", ".spl", ".pks", ".pkb"}


def main(argv):
    if argv[:1] == ["--version"]:
        print(VERSION)
        return 0
    if len(argv) < 5 or argv[1] != "-i" or argv[3] != "-o":
        print("usage: snowct <dialect> -i <input> -o <output>", file=sys.stderr)
        return 2
    dialect, src, out = argv[0], Path(argv[2]), Path(argv[4])
    if dialect not in {"teradata", "oracle", "sql-server", "redshift"}:
        print(f"unknown dialect {dialect}", file=sys.stderr)
        return 3
    code_out = out / "Output" / "SnowConvert"
    reports = out / "Reports" / "SnowConvert"
    reports.mkdir(parents=True, exist_ok=True)
    issues, units = [], []
    for f in sorted(p for p in src.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSIONS):
        rel = f.relative_to(src).as_posix()
        lines_out = []
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for needle, code, sev, name, style in RULES:
                if needle in line.upper():
                    if style == "ewi":
                        lines_out.append(f"!!!RESOLVE EWI!!! /*** {code} - {name.upper()} ***/!!!")
                    else:
                        lines_out.append(f"--** {code} - {name.upper()} **")
                    issues.append([code, sev, name, f"{name} ({needle.strip()})", str(src / rel), n, 1, line.strip()])
            lines_out.append(line.replace("SEL ", "SELECT ").replace("CREATE SET TABLE", "CREATE TABLE"))
        target = code_out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines_out) + "\n")
        units.append([rel, "FILE", rel, f"CU-{len(units) + 1:04d}", str(src / rel),
                      len(lines_out), sum(1 for i in issues if i[4] == str(src / rel) and "EWI" in i[0])])
    with open(reports / "Issues.20261014.090000.csv", "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Code", "Severity", "Name", "Description", "Parent File", "Line", "Column", "Code Snippet"])
        w.writerows(issues)
    with open(reports / "TopLevelCodeUnits.20261014.090000.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Partition Key", "Category", "Code Unit", "Code Unit Id", "File Name", "Lines of Code",
                    "EWI Count", "Conversion Status"])
        for u in units:
            w.writerow(["p1", u[1], u[2], u[3], u[4], u[5], u[6], "Converted with EWIs" if u[6] else "Converted"])
    print(f"Conversion finished: {len(units)} files, {len(issues)} issues")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
