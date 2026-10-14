"""Data Product & Agent Marketplace (Section 26–27).

- ``catalog``  — data product and marketplace-agent manifests (knowledge/marketplace)
- ``trust``    — evidence-based certification from a sealed estate snapshot: a product is certified only when
                 its objects, contract, ownership, documentation, quality monitors, masking and freshness pass;
                 an agent is ready only when its products are certified and it has a role, budget, semantic
                 layer or search service, and an evaluation suite
- ``render``   — Snowflake DDL for secure views, shares and organization listings; Cortex Agent specs
"""

from .catalog import agents, products  # noqa: F401
from .trust import assess  # noqa: F401
