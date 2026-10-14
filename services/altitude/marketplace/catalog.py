"""Manifests for data products and marketplace agents."""

from __future__ import annotations

from altitude.core.knowledge import load_yaml


def products() -> list[dict]:
    return load_yaml("marketplace/products.yaml")["products"]


def agents() -> list[dict]:
    return load_yaml("marketplace/agents.yaml")["marketplace_agents"]


def cross_check() -> list[str]:
    """Agents may only consume products that exist in the catalogue."""
    ids = {p["id"] for p in products()}
    return [f"marketplace/agents.yaml: {a['id']} consumes unknown product {d}"
            for a in agents() for d in a["products"] if d not in ids]


def validate_tree(root) -> list[str]:
    """Hook for ``altitude knowledge validate``: agents reference only catalogued products."""
    import yaml

    try:
        prods = yaml.safe_load((root / "marketplace/products.yaml").read_text())["products"]
        ags = yaml.safe_load((root / "marketplace/agents.yaml").read_text())["marketplace_agents"]
    except (OSError, KeyError, TypeError, yaml.YAMLError):
        return []  # missing or malformed files are reported by the schema pass
    ids = {p["id"] for p in prods}
    return [f"marketplace/agents.yaml: {a['id']} consumes unknown product {d}"
            for a in ags for d in a.get("products", []) if d not in ids]
