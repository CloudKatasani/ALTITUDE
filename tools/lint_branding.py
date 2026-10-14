#!/usr/bin/env python3
"""CI lint: de-branding (white-label) check.

User-facing surfaces must take product/company names and brand colours from
theme tokens (``knowledge/theme/*.yaml``) via ``{{TOKEN}}`` placeholders. This
lint fails if raw brand strings or hex colours appear in:

- ``portal/**`` (except ``portal/**/tokens*``),
- any ``templates/`` directory under ``services/``, ``agents/`` or ``skills/``.

Brand strings are read from the default theme, so the check follows renames.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b")
TEXT_SUFFIXES = {".html", ".htm", ".css", ".js", ".ts", ".tsx", ".jsx", ".md", ".j2", ".txt", ".json", ".yaml", ".svg"}


def brand_terms(root: Path) -> list[str]:
    toks = yaml.safe_load((root / "knowledge/theme/default.yaml").read_text())["tokens"]
    terms = {toks["PRODUCT_NAME"], toks["COMPANY_NAME"], toks["COPILOT_NAME"]}
    return sorted(t for t in terms if t)


def candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    portal = root / "portal"
    if portal.exists():
        files += [p for p in portal.rglob("*") if p.is_file() and "tokens" not in p.name and "node_modules" not in p.parts]
    for base in ("services", "agents", "skills"):
        b = root / base
        if b.exists():
            for tdir in b.rglob("templates"):
                if tdir.is_dir():
                    files += [p for p in tdir.rglob("*") if p.is_file()]
    return sorted(p for p in files if p.suffix in TEXT_SUFFIXES)


def lint(root: Path) -> list[str]:
    terms = brand_terms(root)
    pattern = re.compile("|".join(re.escape(t) for t in terms))  # brand names are matched case-sensitively
    problems = []
    for f in candidate_files(root):
        for i, line in enumerate(f.read_text(errors="replace").splitlines(), 1):
            if pattern.search(line):
                problems.append(f"{f.relative_to(root)}:{i}: raw brand string; use a {{{{TOKEN}}}} placeholder")
            if HEX.search(line):
                problems.append(f"{f.relative_to(root)}:{i}: raw colour; use a COLOR_* theme token")
    return problems


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[1]
    problems = lint(root)
    for p in problems:
        print(p)
    print(f"lint_branding: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
