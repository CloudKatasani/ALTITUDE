import pytest
from fastapi.testclient import TestClient

from altitude.advisory.facts import coerce, fact_specs, parse
from altitude.api.app import create_app
from altitude.core.store import Store


def H(role="delivery_lead", user="lead@acme"):
    return {"X-Altitude-User": user, "X-Altitude-Role": role}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTITUDE_AUTH", "dev")
    c = TestClient(create_app(store=Store(), workspace=tmp_path))
    eng = c.post("/api/v1/engagements", headers=H(), json={"tenant": "Acme", "client": "Acme Utilities",
                                                            "package": "D2", "name": "Acme Package D"}).json()
    return c, eng["engagement_id"]


def test_typed_parsing():
    s = fact_specs()
    assert coerce(s["test_harness"], "no") is False and coerce(s["test_harness"], "") is None
    assert coerce(s["procedural_object_count"], "4200") == 4200
    assert coerce(s["dead_object_share"], "0.42") == 0.42
    assert coerce(s["decommission_date"], "2027-03-31") == "2027-03-31"
    for key, bad in [("procedural_object_count", "lots"), ("dead_object_share", "1.5"), ("pattern", "yolo"),
                     ("decommission_date", "31/03/2027"), ("test_harness", "maybe")]:
        with pytest.raises(ValueError):
            coerce(s[key], bad)
    changes, errors = parse({"pattern": "re_platform", "deadline_weeks": "20", "unknown": "x"}, {"pattern": "re_platform"})
    assert changes == {"deadline_weeks": 20} and errors == {}


def test_form_saves_changes_and_drives_challenges(client):
    c, eid = client
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    page = c.get("/facts")
    assert page.status_code == 200 and "Procedural objects / scripts" in page.text and "Save facts" in page.text
    r = c.post("/facts", data={"engagement_id": eid, "pattern": "lift_and_shift", "procedural_object_count": "4200",
                               "test_harness": "no", "deadline_weeks": ""}, follow_redirects=True)
    assert "Saved: pattern, procedural_object_count, test_harness" in r.text
    assert "SH-CH-001" in r.text  # live preview of Sherpa's challenges
    assert "SH-CH-001" in c.get("/").text
    assert c.get(f"/api/v1/engagements/{eid}/facts", headers=H()).json() == {
        "pattern": "lift_and_shift", "procedural_object_count": 4200, "test_harness": False}
    # clearing a field removes the fact; challenge disappears
    c.post("/facts", data={"engagement_id": eid, "test_harness": "yes"})
    assert "SH-CH-001" not in c.get("/").text
    c.post("/facts", data={"engagement_id": eid, "pattern": ""})
    assert "pattern" not in c.get(f"/api/v1/engagements/{eid}/facts", headers=H()).json()
    trail = c.get("/api/v1/audit", headers=H(), params={"subject_type": "engagement", "subject_id": eid}).json()
    assert sum(1 for t in trail if t["action"] == "engagement.facts") == 3


def test_invalid_input_saves_nothing_and_shows_errors(client):
    c, eid = client
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    r = c.post("/facts", data={"engagement_id": eid, "procedural_object_count": "-5", "pattern": "lift_and_shift"})
    assert r.status_code == 422 and "must be at least 0" in r.text and "Nothing was saved" in r.text
    assert 'value="-5"' in r.text  # the user's input is kept for correction
    assert c.get(f"/api/v1/engagements/{eid}/facts", headers=H()).json() == {}
    bad = c.put(f"/api/v1/engagements/{eid}/facts", headers=H(), json={"facts": {"dead_object_share": 3}})
    assert bad.status_code == 422


def test_read_only_roles_cannot_edit(client):
    c, eid = client
    c.post("/login", data={"user": "viewer@acme", "role": "client_viewer"})
    page = c.get("/facts").text
    assert "can view but not edit" in page and "Save facts" not in page
    assert c.post("/facts", data={"engagement_id": eid, "pattern": "re_platform"}).status_code == 403
