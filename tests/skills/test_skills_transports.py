"""The module skills are reachable over both transports that share the registry: MCP and REST."""

import json

from fastapi.testclient import TestClient

from altitude.api.app import create_app
from altitude.core.store import Store
from altitude.mcp.server import MCPServer
from altitude.skills.context import SkillContext

SQL = "SELECT id FROM customers WHERE middle_name = ''"


def test_mcp_lists_and_calls_module_skills(tmp_path):
    server = MCPServer(context=SkillContext.from_workspace(tmp_path))
    tools = {t["name"]: t for t in server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]}
    assert {"run_diagnostic", "plan_waves", "generate_rbac_from_legacy_grants", "run_agent"} <= set(tools)
    assert tools["scan_drift"]["inputSchema"]["required"] == ["sql", "dialect"]
    res = server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "scan_drift", "arguments": {"sql": SQL, "dialect": "oracle"}}})["result"]
    assert res["isError"] is False and "OR-01" in json.loads(res["content"][0]["text"])["issues"]
    bad = server.handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                         "params": {"name": "run_diagnostic", "arguments": {"snapshot_id": "SNAP-MISSING"}}})["result"]
    assert bad["isError"] is True and "unknown snapshot" in bad["content"][0]["text"]


def test_rest_invokes_module_skills_with_rbac(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTITUDE_AUTH", "dev")
    client = TestClient(create_app(store=Store(), workspace=tmp_path))
    lead = {"X-Altitude-User": "lead@acme", "X-Altitude-Role": "delivery_lead"}
    viewer = {"X-Altitude-User": "cv@client", "X-Altitude-Role": "client_viewer"}
    listed = {s["name"]: s for s in client.get("/api/v1/skills", headers=lead).json()}
    assert listed["harvest_source"]["available"] and listed["scan_drift"]["permission"] == "read"
    r = client.post("/api/v1/skills/scan_drift", headers=viewer, json={"sql": SQL, "dialect": "oracle"})
    assert r.status_code == 200 and r.json()["summary"]["hits"] >= 1
    assert client.post("/api/v1/skills/harvest_source", headers=viewer, json={"source": "oracle"}).status_code == 403
    h = client.post("/api/v1/skills/harvest_source", headers=lead, json={"source": "oracle", "engagement_id": "ENG-API"})
    assert h.status_code == 200 and h.json()["counts"]["grant"] > 0
    rbac = client.post("/api/v1/skills/generate_rbac_from_legacy_grants", headers=lead,
                       json={"source_system_id": h.json()["source_system_id"]})
    assert rbac.status_code == 200 and rbac.json()["grants"] == h.json()["counts"]["grant"]
    assert client.post("/api/v1/skills/run_well_architected_check", headers=lead,
                       json={"snapshot_id": "SNAP-MISSING"}).status_code == 422
