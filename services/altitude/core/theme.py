"""White-label theme tokens (``knowledge/theme/<name>.yaml``).

All user-facing strings use ``{{PRODUCT_NAME}}``-style placeholders rendered
through :func:`render`. The de-branding lint (``tools/lint_branding.py``) fails
if raw brand strings or colours appear outside token files.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache

import yaml

from .paths import knowledge_dir

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Z][A-Z0-9_]*)\s*\}\}")


@lru_cache(maxsize=8)
def tokens(theme: str | None = None) -> dict[str, str]:
    theme = theme or os.environ.get("ALTITUDE_THEME", "default")
    path = knowledge_dir() / "theme" / f"{theme}.yaml"
    return dict(yaml.safe_load(path.read_text())["tokens"])


def token(name: str, theme: str | None = None) -> str:
    return tokens(theme)[name]


def render(text: str, theme: str | None = None, **extra: str) -> str:
    """Replace ``{{TOKEN}}`` placeholders with theme tokens (and ``extra`` values)."""
    toks = {**tokens(theme), **extra}

    def sub(m: re.Match) -> str:
        key = m.group(1)
        return toks[key] if key in toks else m.group(0)

    return _PLACEHOLDER.sub(sub, text)
