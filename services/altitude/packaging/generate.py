"""``generated/packaging/native_app/*`` — the Native App bundle (stamped)."""

from __future__ import annotations

from altitude.core.generated import stamp

from .native_app import bundle


def generate() -> dict[str, str]:
    out = {}
    for name, content in bundle().items():
        suffix = "." + name.rsplit(".", 1)[1]
        out[f"packaging/native_app/{name}"] = stamp(content, ".yaml" if suffix == ".yml" else suffix,
                                                    "altitude.packaging.native_app (harvest contract + check catalogue)")
    return out
