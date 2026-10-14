"""Executable skills (Section 17.4).

Skill manifests live in ``skills/*.yaml`` at the repository root::

    name: run_well_architected_check
    description: ...
    permission: run            # RBAC permission needed (knowledge/api/rbac.yaml)
    entrypoint: altitude.skills.impl:run_well_architected_check
    input_schema: {type: object, properties: {...}, required: [...]}

The same registry backs the REST API (``/api/v1/skills``) and the MCP server, so
every client — portal, Claude, Cursor, Cortex Code, Copilot — calls identical code.
"""

from .registry import Skill, SkillError, load_skills, run_skill  # noqa: F401
