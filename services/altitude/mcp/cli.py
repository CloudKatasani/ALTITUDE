"""``altitude mcp`` — run the MCP server on stdio."""

from __future__ import annotations

import argparse


def _cmd_mcp(args: argparse.Namespace) -> int:
    from altitude.skills.context import SkillContext

    from .server import MCPServer

    MCPServer(context=SkillContext.from_workspace(args.workspace)).serve()
    return 0


def _cmd_skills(args: argparse.Namespace) -> int:
    from altitude.skills import load_skills

    for s in load_skills().values():
        print(f"{s.name:34s} {'available' if s.available else 'unavailable':12s} {s.permission:8s} {s.description}")
    return 0


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("mcp", help="run the MCP server (stdio) exposing skills as tools")
    p.add_argument("--workspace", default=".altitude")
    p.set_defaults(func=_cmd_mcp)
    s = sub.add_parser("skills", help="list executable skills")
    s.set_defaults(func=_cmd_skills)
