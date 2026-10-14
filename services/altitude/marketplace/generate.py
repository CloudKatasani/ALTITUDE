"""``generated/marketplace/*`` — listings and agent specs rendered from the manifests (stamped).

These are the renderings of every manifest; publishing to a real account is gated by certification
(``altitude marketplace publish``), which emits SQL only for products and agents that pass on a snapshot.
"""

from __future__ import annotations

from altitude.core.generated import stamp

from .catalog import agents, products
from .render import agent_sql, catalogue_markdown, product_sql


def generate() -> dict[str, str]:
    prods, ags = products(), agents()
    by_id = {p["id"]: p for p in prods}
    src = "knowledge/marketplace"
    out = {"marketplace/catalogue.md": stamp(catalogue_markdown(prods, ags), ".md", src)}
    for p in prods:
        out[f"marketplace/products/{p['id']}.sql"] = stamp(product_sql(p), ".sql", f"{src}/products.yaml")
    for a in ags:
        out[f"marketplace/agents/{a['id']}.sql"] = stamp(agent_sql(a, by_id), ".sql", f"{src}/agents.yaml")
    return out
