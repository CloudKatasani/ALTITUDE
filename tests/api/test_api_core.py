import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from altitude.api import auth
from altitude.api.app import create_app
from altitude.core.ai import Inference, ReviewQueue
from altitude.core.store import Store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTITUDE_AUTH", "dev")
    store = Store()
    app = create_app(store=store, workspace=tmp_path)
    return TestClient(app), store


def H(role="delivery_lead", user="lead@acme"):
    return {"X-Altitude-User": user, "X-Altitude-Role": role}


def test_auth_and_rbac(client):
    c, _ = client
    assert c.get("/api/v1/health").json()["status"] == "ok"
    assert c.get("/api/v1/me").status_code == 401
    assert c.get("/api/v1/me", headers=H()).json()["role"] == "delivery_lead"
    assert c.get("/api/v1/me", headers=H(role="root")).status_code == 401
    r = c.post("/api/v1/review-board", headers=H(role="client_viewer"), json={"title": "x", "facts": {}})
    assert r.status_code == 403


def test_review_queue_flow(client):
    c, store = client
    ReviewQueue(store).record(Inference("narrative", "suggestion", "SUG-9", "t", 0.5, "weak", "m", "t@1"))
    items = c.get("/api/v1/review-queue", headers=H()).json()
    assert items[0]["subject_id"] == "SUG-9"
    iid = items[0]["item_id"]
    assert c.post(f"/api/v1/review-queue/{iid}/decision", headers=H(role="client_viewer"),
                  json={"decision": "approved"}).status_code == 403
    r = c.post(f"/api/v1/review-queue/{iid}/decision", headers=H(), json={"decision": "approved"})
    assert r.json()["reviewer"] == "lead@acme"
    assert c.get("/api/v1/review-queue", headers=H()).json() == []
    trail = c.get("/api/v1/audit", headers=H(), params={"subject_type": "review_item", "subject_id": iid}).json()
    assert trail[0]["action"] == "review.approved"


def test_sherpa_and_board_endpoints(client):
    c, _ = client
    r = c.post("/api/v1/sherpa/ask", headers=H(), json={"question": "weather in Paris tomorrow"}).json()
    assert r["grounded"] is False
    board = c.post("/api/v1/review-board", headers=H(), json={
        "title": "Wave 1", "facts": {"pattern": "re_platform", "modernise_backlog": True}, "engagement_id": "ENG-1"}).json()
    assert len(board["perspectives"]) == 7
    assert c.post(f"/api/v1/review-board/{board['decision_id']}/decision", headers=H(role="engineer"),
                  json={"decision": "accepted"}).status_code == 403
    ok = c.post(f"/api/v1/review-board/{board['decision_id']}/decision", headers=H(role="exec"),
                json={"decision": "accepted"})
    assert ok.json()["status"] == "accepted"


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _is_prime(n: int) -> bool:
    if n < 2:
        return False
    for sp in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % sp == 0:
            return n == sp
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(seed: int) -> int:
    c = int.from_bytes(hashlib.sha512(f"altitude-test-{seed}".encode()).digest(), "big") | (1 << 511) | 1
    while not (_is_prime(c) and (c - 1) % 65537):
        c += 2
    return c


def test_hs256_and_rs256_tokens(monkeypatch):
    tok = auth.sign_hs256({"sub": "svc", "altitude_role": "engineer", "exp": 4102444800}, "s3cret")
    assert auth.principal_from_claims(auth.verify_jwt(tok, secret="s3cret")).role == "engineer"
    with pytest.raises(auth.AuthError):
        auth.verify_jwt(tok, secret="wrong")
    expired = auth.sign_hs256({"sub": "svc", "altitude_role": "engineer", "exp": 1}, "s3cret")
    with pytest.raises(auth.AuthError):
        auth.verify_jwt(expired, secret="s3cret")

    # RS256 with a deterministic 1024-bit test-only RSA key
    p, q = _prime(1), _prime(2)
    n, e = p * q, 65537
    d = pow(e, -1, (p - 1) * (q - 1))
    k = (n.bit_length() + 7) // 8
    h = _b64(json.dumps({"alg": "RS256", "kid": "k1"}).encode())
    pl = _b64(json.dumps({"sub": "u", "altitude_role": "exec", "exp": 4102444800}).encode())
    digest = auth._SHA256_PREFIX + hashlib.sha256(f"{h}.{pl}".encode()).digest()
    pad = k - len(digest) - 3
    if pad < 8:
        pytest.skip("test key too small for PKCS#1 v1.5 SHA-256")
    em = b"\x00\x01" + b"\xff" * pad + b"\x00" + digest
    sig = pow(int.from_bytes(em, "big"), d, n).to_bytes(k, "big")
    jwks = {"keys": [{"kid": "k1", "kty": "RSA", "n": _b64(n.to_bytes(k, "big")), "e": _b64(e.to_bytes(3, "big"))}]}
    claims = auth.verify_jwt(f"{h}.{pl}.{_b64(sig)}", jwks=jwks)
    assert claims["altitude_role"] == "exec"
    tampered = sig[:-1] + bytes([sig[-1] ^ 1])
    with pytest.raises(auth.AuthError):
        auth.verify_jwt(f"{h}.{pl}.{_b64(tampered)}", jwks=jwks)


def test_portal_pages_render_with_theme(client):
    c, store = client
    from altitude.api.app import Context  # noqa: F401
    assert c.get("/app", follow_redirects=False).status_code == 303
    c.post("/login", data={"user": "lead@acme", "role": "delivery_lead"})
    c.post("/api/v1/engagements", headers=H(), json={"tenant": "Acme", "client": "Acme Utilities",
                                                      "package": "D2", "name": "Acme Package D"})
    home = c.get("/app")
    assert home.status_code == 200 and "Acme Package D" in home.text and "Next three actions" in home.text
    assert "ALTITUDE" in home.text  # from the theme token, not the template
    for path in ("/review", "/sherpa?q=idle+warehouses", "/decisions"):
        assert c.get(path).status_code == 200


def test_white_label_partner_theme_is_configuration_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ALTITUDE_AUTH", "dev")
    monkeypatch.setenv("ALTITUDE_THEME", "partner_example")
    c = TestClient(create_app(store=Store(), workspace=tmp_path))
    c.post("/login", data={"user": "p@x", "role": "partner_admin"})
    for path in ("/app", "/review", "/sherpa", "/decisions", "/login"):
        html = c.get(path).text
        assert "Summit Insight" in html and "ALTITUDE" not in html and "Sherpa" not in html, path
