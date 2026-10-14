"""End to end through the API: engagement -> sealed snapshot -> Package D -> evidence drill-through ->
grounded Sherpa -> human lifecycle decisions -> progress board -> portal pages."""

import re

import pytest
from fastapi.testclient import TestClient

from altitude.api.app import create_app
from altitude.core.store import Store


def H(role="delivery_lead", user="lead@acme"):
    return {"X-Altitude-User": user, "X-Altitude-Role": role}


@pytest.fixture(scope="module")
def flow(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("ALTITUDE_AUTH", "dev")
    ws = tmp_path_factory.mktemp("ws")
    c = TestClient(create_app(store=Store(), workspace=ws))
    eng = c.post("/api/v1/engagements", headers=H(), json={"tenant": "Acme", "client": "Acme Utilities",
                                                            "package": "D2", "name": "Acme Package D"}).json()
    snap = c.post("/api/v1/skills/build_synthetic_snapshot", headers=H(), json={"profile": "seeded", "days": 90}).json()
    run = c.post("/api/v1/diagnostics/runs", headers=H(), json={"snapshot_id": snap["snapshot_id"], "tier": "D2",
                                                                "engagement_id": eng["engagement_id"]}).json()
    yield c, eng, snap, run
    mp.undo()


def test_run_publishes_evidence_backed_suggestions(flow):
    c, _, snap, run = flow
    assert run["snapshot_id"] == snap["snapshot_id"] and run["suggestions"] >= 30
    assert "suggestions.json" in run["exports"]
    sugg = c.get("/api/v1/diagnostics/suggestions", headers=H()).json()
    idle = next(s for s in sugg if s["check_id"] == "DX-COST-01")
    d = c.get(f"/api/v1/diagnostics/suggestions/{idle['suggestion_id']}", headers=H()).json()
    assert d["evidence"] and all(e["evidence_id"].startswith("EV-") for e in d["evidence"])
    assert d["suggestion"]["value"]["method"] and d["suggestion"]["remediation"]["rollback_ref"]
    ev = c.get(f"/api/v1/diagnostics/evidence/{d['evidence'][0]['evidence_id']}", headers=H()).json()
    assert idle["suggestion_id"] in ev["suggestions"]
    assert c.get(f"/api/v1/diagnostics/runs/{run['run_id']}/exports/suggestions.json", headers=H()).status_code == 200
    assert c.get(f"/api/v1/diagnostics/runs/{run['run_id']}/exports/..%2F..%2Fcontrol.duckdb",
                 headers=H()).status_code == 404


def test_sherpa_is_grounded_in_the_run(flow):
    c, *_ = flow
    ans = c.post("/api/v1/sherpa/ask", headers=H(), json={"question": "Which warehouses are idle-heavy?"}).json()
    assert ans["grounded"] and any(x.startswith(("SUG-", "EV-")) for x in ans["citations"])
    assert not c.post("/api/v1/sherpa/ask", headers=H(), json={"question": "Who won the 1966 World Cup?"}).json()["grounded"]


def test_lifecycle_needs_humans_and_board_links_ids(flow):
    c, *_ = flow
    sugg = c.get("/api/v1/diagnostics/suggestions", headers=H()).json()
    sid = next(s["suggestion_id"] for s in sugg if not s["needs_review"])
    assert c.post(f"/api/v1/diagnostics/suggestions/{sid}/transition", headers=H(role="engineer"),
                  json={"to_status": "accepted"}).status_code == 403
    ok = c.post(f"/api/v1/diagnostics/suggestions/{sid}/transition", headers=H(), json={"to_status": "accepted"})
    assert ok.status_code == 200, ok.text
    board = c.get("/api/v1/diagnostics/progress", headers=H()).json()
    assert sid in board["by_status"]["accepted"]["ids"]
    assert board["identified"]["count"] == len(board["identified"]["ids"]) == len(sugg)
    assert board["identified"]["value_p50_usd"] > 0


def test_portal_pages_link_numbers_to_evidence(flow):
    c, *_ = flow
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    page = c.get("/findings").text
    assert "DX-COST-01" in page and re.search(r'/api/v1/diagnostics/evidence/EV-', page)
    sid = re.search(r'/suggestion\?id=(SUG-[A-Z0-9-]+)', page).group(1)
    detail = c.get(f"/suggestion?id={sid}").text
    assert "Evidence" in detail and "EV-" in detail
    assert "identified vs realised" in c.get("/progress").text
    assert c.get("/agents").status_code == 200 and c.get("/dashboards").status_code == 200


def test_board_pack_skill(flow):
    c, _, snap, _ = flow
    out = c.post("/api/v1/skills/generate_board_pack", headers=H(), json={"snapshot_id": snap["snapshot_id"]}).json()
    assert out["snapshot_id"] == snap["snapshot_id"] and "board_pack.pdf" in out["files"]


def test_engagement_facts_drive_home_page_challenges(flow):
    c, eng, *_ = flow
    facts = {"pattern": "lift_and_shift", "procedural_object_count": 4200, "test_harness": False}
    assert c.put(f"/api/v1/engagements/{eng['engagement_id']}/facts", headers=H(role="client_viewer"),
                 json={"facts": facts}).status_code == 403
    stored = c.put(f"/api/v1/engagements/{eng['engagement_id']}/facts", headers=H(), json={"facts": facts}).json()
    assert stored == facts
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    home = c.get("/app").text
    assert "SH-CH-001" in home and "4200 procedural scripts" in home
    c.put(f"/api/v1/engagements/{eng['engagement_id']}/facts", headers=H(), json={"facts": {"test_harness": True}})
    assert "SH-CH-001" not in c.get("/app").text  # latest value wins


def test_sherpa_evidence_is_readable_not_raw_json(flow):
    c, *_ = flow
    ans = c.post("/api/v1/sherpa/ask", headers=H(), json={"question": "idle share of WH_DEV warehouse"}).json()
    assert ans["grounded"]
    ev_lines = [l for l in ans["answer"].splitlines() if l.startswith("- [EV-")]
    assert ev_lines and all("{" not in l and '"' not in l for l in ev_lines)
    assert any("Idle share" in l and "%" in l for l in ev_lines)


def test_agents_page_separates_approvals_from_advice(flow):
    c, _, snap, _ = flow
    c.post("/api/v1/agents/AG-ACCESS-HYGIENE/evals?promote=true", headers=H())
    c.post("/api/v1/agents/AG-ACCESS-HYGIENE/runs", headers=H(), json={"snapshot_id": snap["snapshot_id"]})
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    html = c.get("/agents").text
    approvals, rest = html.split("Recommendations (advice only", 1)
    advice = rest.split("Action log", 1)[0]
    assert "grant.revoke_role_from_user" in approvals and ">L1<" not in approvals
    assert "orphan_role:ROLE_LEGACY_MKTG" in advice and ">L1<" in advice
