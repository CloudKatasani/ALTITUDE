import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from altitude.api.app import create_app
from altitude.core.store import Store
from altitude.website.build import PAGES, render_site
from altitude.website.samples import collect


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    samples = collect(root / "cache", root / "out")
    return root, samples, render_site(samples)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in ("href", "src") and v:
                self.hrefs.append(v)


def test_every_offering_and_page_is_rendered(built):
    _, samples, files = built
    assert {p[0] for p in PAGES} <= set(files)
    from altitude.core.knowledge import load_yaml

    offers = load_yaml("commercial/catalog.yaml")["offers"]
    offerings = files["offerings.html"]
    for o in offers:
        assert f'id="{o["id"]}"' in offerings and o["name"] in offerings
    assert "{{" not in "".join(files.values())  # every theme token rendered
    assert "Section 6" not in offerings and "Free + " not in offerings  # catalogue copy, not spec references


def test_internal_links_resolve(built):
    root, _, files = built
    out = root / "out"
    for name, html in files.items():
        if not name.endswith(".html"):
            continue
        p = Links()
        p.feed(html)
        for href in p.hrefs:
            if href.startswith(("http", "mailto:", "/", "#")):
                continue
            target = href.split("#")[0]
            assert target in files or (out / target).exists(), f"{name}: broken link {href}"


def test_samples_are_real_and_labelled_synthetic(built):
    _, s, files = built
    assert s["suggestions"] >= 30 and s["value_p50"] > 0 and 0 <= s["phi"] <= 100
    assert all(t["evidence_refs"] for t in s["top"])
    assert {"TD-01", "TD-02"} <= {h["issue_id"] for h in s["drift"]["teradata"]}
    assert s["observability"]["ask"]["citations"] == ["KPI-COST-007"]
    assert len({(a["alert"], a["object"]) for a in s["observability"]["alerts"]}) == len(s["observability"]["alerts"])
    home = files["index.html"]
    assert f"{s['value_p50']:,.0f}" in home and "synthetic" in home.lower()
    for name in ("index.html", "package-d.html", "package-o.html", "ai-ready.html"):
        assert "synthetic" in files[name].lower(), name


def test_white_label_site(built):
    _, samples, _ = built
    partner = render_site(samples, theme="partner_example")
    joined = "".join(v for k, v in partner.items() if k.endswith(".html"))
    assert "Summit Insight" in joined and "ALTITUDE" not in joined


def test_public_site_and_contact_via_api(built, tmp_path, monkeypatch):
    _, samples, _ = built
    monkeypatch.setenv("ALTITUDE_AUTH", "dev")
    app = create_app(store=Store(), workspace=tmp_path)
    app.state.ctx.extras["site_samples"] = samples
    c = TestClient(app)
    home = c.get("/")
    assert home.status_code == 200 and "Book a free D0 Snapshot" in home.text and 'href="/login"' in home.text
    for f, *_ in PAGES:
        assert c.get(f"/{f}").status_code == 200, f
    assert c.get("/assets/site.css").headers["content-type"].startswith("text/css")
    assert c.get("/nope.html").status_code == 404
    assert c.get("/samples/..%2F..%2Fcontrol.duckdb").status_code == 404
    form = c.get("/contact.html").text
    assert 'action="/contact"' in form
    r = c.post("/contact", data={"name": "Pat Lee", "email": "pat@grid.example", "company": "Grid Co",
                                 "spend": "$1M–$5M", "interest": "OFF-D0", "message": "AMI estate"})
    assert r.status_code == 200 and "Thank you, Pat" in r.text
    sig = app.state.ctx.store.query("SELECT * FROM gtm_signal")
    assert sig[0]["account"] == "Grid Co" and sig[0]["kind"] == "inbound_request" and "OFF-D0" in sig[0]["detail"]
    assert c.post("/contact", data={"name": "x", "email": "nope", "company": "y"}).status_code == 422
    # the portal still works behind sign-in
    assert c.get("/app", follow_redirects=False).status_code == 303
