"""Model Context Protocol server (JSON-RPC 2.0 over stdio, newline-delimited).

Implements ``initialize``, ``ping``, ``tools/list`` and ``tools/call`` and exposes
every available skill from the registry as a tool. Tool calls run with the
principal configured for the server process (``ALTITUDE_MCP_ROLE``, default
``engineer``) so RBAC applies to AI clients exactly as to people. Tool output is
data for the client; skills never take instructions from tool arguments beyond
their schema.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, IO

from altitude import __version__
from altitude.api.auth import Principal
from altitude.core.store import json_safe
from altitude.core.theme import token
from altitude.skills import SkillError, load_skills, run_skill

PROTOCOL_VERSION = "2025-06-18"


class MCPServer:
    def __init__(self, context: Any = None, principal: Principal | None = None):
        self.context = context
        self.principal = principal or Principal(user=os.environ.get("ALTITUDE_MCP_USER", "mcp-client"),
                                                role=os.environ.get("ALTITUDE_MCP_ROLE", "engineer"))

    def tools(self) -> list[dict]:
        return [s.tool_spec() for s in load_skills().values()
                if s.available and self.principal.can(s.permission)]

    def handle(self, msg: dict) -> dict | None:
        mid = msg.get("id")
        method = msg.get("method")
        if mid is None:  # notification (e.g. notifications/initialized)
            return None
        try:
            if method == "initialize":
                result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                          "serverInfo": {"name": token("PRODUCT_NAME").lower() + "-mcp", "version": __version__},
                          "instructions": "Tools return evidence-backed results; cite the evidence IDs they return."}
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.tools()}
            elif method == "tools/call":
                params = msg.get("params") or {}
                result = self._call(params.get("name"), params.get("arguments") or {})
            else:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
        except Exception as e:  # noqa: BLE001 - protocol boundary
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _call(self, name: str, arguments: dict) -> dict:
        try:
            out = run_skill(name, arguments, context=self.context, principal=self.principal)
        except SkillError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        payload = json.dumps(json_safe(out), indent=2, default=str)
        return {"content": [{"type": "text", "text": payload}], "structuredContent": json_safe(out)
                if isinstance(out, dict) else {"result": json_safe(out)}, "isError": False}

    def serve(self, stdin: IO[str] = sys.stdin, stdout: IO[str] = sys.stdout) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                resp: dict | None = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
            else:
                resp = self.handle(msg)
            if resp is not None:
                stdout.write(json.dumps(resp) + "\n")
                stdout.flush()
