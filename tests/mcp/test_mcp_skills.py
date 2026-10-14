import io
import json

from altitude.api.auth import Principal
from altitude.mcp.server import MCPServer
from altitude.skills import load_skills
from altitude.skills.context import SkillContext


def _rpc(server, method, params=None, mid=1):
    return server.handle({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})


def test_skill_manifests_valid_and_entrypoints_resolve():
    skills = load_skills()
    assert {"ask_sherpa", "review_decision", "validate_knowledge"} <= set(skills)
    assert all(s.available for s in skills.values()), [s.name for s in skills.values() if not s.available]


def test_mcp_protocol_roundtrip(tmp_path):
    server = MCPServer(context=SkillContext.from_workspace(tmp_path))
    init = _rpc(server, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert init["result"]["capabilities"]["tools"] is not None
    assert server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    tools = {t["name"] for t in _rpc(server, "tools/list")["result"]["tools"]}
    assert "ask_sherpa" in tools
    res = _rpc(server, "tools/call", {"name": "ask_sherpa", "arguments": {"question": "what is the meaning of life"}})
    body = json.loads(res["result"]["content"][0]["text"])
    assert body["grounded"] is False and res["result"]["isError"] is False
    bad = _rpc(server, "tools/call", {"name": "ask_sherpa", "arguments": {"nope": 1}})
    assert bad["result"]["isError"] is True
    assert _rpc(server, "no/such")["error"]["code"] == -32601


def test_mcp_rbac_applies_to_ai_clients(tmp_path):
    viewer = MCPServer(context=SkillContext.from_workspace(tmp_path), principal=Principal("bot", "client_viewer"))
    names = {t["name"] for t in _rpc(viewer, "tools/list")["result"]["tools"]}
    assert "review_decision" not in names and "ask_sherpa" in names
    denied = _rpc(viewer, "tools/call", {"name": "review_decision", "arguments": {"title": "x y z", "facts": {}}})
    assert denied["result"]["isError"] and "lacks permission" in denied["result"]["content"][0]["text"]


def test_stdio_transport(tmp_path):
    server = MCPServer(context=SkillContext.from_workspace(tmp_path))
    inp = io.StringIO(json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\nnot json\n")
    out = io.StringIO()
    server.serve(inp, out)
    lines = [json.loads(l) for l in out.getvalue().splitlines()]
    assert lines[0] == {"jsonrpc": "2.0", "id": 7, "result": {}}
    assert lines[1]["error"]["code"] == -32700
