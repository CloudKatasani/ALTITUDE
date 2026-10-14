"""Authentication and RBAC for the API and portal.

Supported bearer tokens (JWT):
- **RS256** verified against the identity provider's JWKS (OIDC SSO). Verification
  is implemented with the standard library (RSASSA-PKCS1-v1_5 / SHA-256), so no
  private key material is ever needed by the platform.
- **HS256** with a tenant secret (``ALTITUDE_JWT_SECRET``) for service-to-service
  calls and the partner edition.
Claims used: ``sub`` (user), ``altitude_role`` (or ``roles``), ``tenant``, ``exp``.

``ALTITUDE_AUTH=dev`` enables header auth (``X-Altitude-User``/``X-Altitude-Role``)
for local development and tests only.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from altitude.core.knowledge import load_yaml

# DER prefix of DigestInfo for SHA-256 (RFC 8017 §9.2 note 1)
_SHA256_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


class AuthError(Exception):
    pass


@dataclass(frozen=True)
class Principal:
    user: str
    role: str
    tenant: str | None = None

    def can(self, permission: str) -> bool:
        return permission in role_permissions(self.role)


@lru_cache(maxsize=1)
def _rbac() -> dict:
    return load_yaml("api/rbac.yaml")["roles"]


def role_permissions(role: str) -> set[str]:
    r = _rbac().get(role)
    return set(r["permissions"]) if r else set()


def roles() -> list[str]:
    return sorted(_rbac())


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _rs256_verify(signing_input: bytes, signature: bytes, n: int, e: int) -> bool:
    k = (n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    m = pow(int.from_bytes(signature, "big"), e, n).to_bytes(k, "big")
    digest_info = _SHA256_PREFIX + hashlib.sha256(signing_input).digest()
    pad_len = k - len(digest_info) - 3
    if pad_len < 8:
        return False
    expected = b"\x00\x01" + b"\xff" * pad_len + b"\x00" + digest_info
    return hmac.compare_digest(m, expected)


def verify_jwt(token: str, *, secret: str | None = None, jwks: dict | None = None, now: float | None = None) -> dict:
    try:
        h64, p64, s64 = token.split(".")
        header = json.loads(_b64d(h64))
        claims = json.loads(_b64d(p64))
        sig = _b64d(s64)
    except Exception as e:  # noqa: BLE001
        raise AuthError(f"malformed token: {e}") from None
    signing_input = f"{h64}.{p64}".encode()
    alg = header.get("alg")
    if alg == "HS256":
        if not secret:
            raise AuthError("HS256 token but no tenant secret configured")
        if not hmac.compare_digest(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest(), sig):
            raise AuthError("bad signature")
    elif alg == "RS256":
        keys = (jwks or {}).get("keys", [])
        key = next((k for k in keys if k.get("kid") == header.get("kid")), keys[0] if len(keys) == 1 else None)
        if key is None:
            raise AuthError("no matching JWKS key")
        n = int.from_bytes(_b64d(key["n"]), "big")
        e = int.from_bytes(_b64d(key["e"]), "big")
        if not _rs256_verify(signing_input, sig, n, e):
            raise AuthError("bad signature")
    else:
        raise AuthError(f"unsupported alg {alg!r}")
    if "exp" in claims and float(claims["exp"]) < (now or time.time()):
        raise AuthError("token expired")
    return claims


def sign_hs256(claims: dict, secret: str) -> str:
    h = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = _b64e(json.dumps(claims).encode())
    sig = hmac.new(secret.encode(), f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{_b64e(sig)}"


def principal_from_claims(claims: dict) -> Principal:
    role = claims.get("altitude_role") or next(iter(claims.get("roles") or []), None)
    if role not in _rbac():
        raise AuthError(f"unknown or missing role {role!r}")
    return Principal(user=str(claims.get("sub")), role=role, tenant=claims.get("tenant"))


def authenticate(headers: Any) -> Principal:
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        jwks = None
        jwks_path = os.environ.get("ALTITUDE_JWKS_FILE")
        if jwks_path:
            with open(jwks_path) as fh:
                jwks = json.load(fh)
        claims = verify_jwt(auth[7:], secret=os.environ.get("ALTITUDE_JWT_SECRET"), jwks=jwks)
        return principal_from_claims(claims)
    if os.environ.get("ALTITUDE_AUTH") == "dev":
        user, role = headers.get("x-altitude-user"), headers.get("x-altitude-role")
        if user and role in _rbac():
            return Principal(user=user, role=role, tenant=headers.get("x-altitude-tenant"))
    raise AuthError("authentication required")
