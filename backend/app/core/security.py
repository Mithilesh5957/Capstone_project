"""Auth helpers: mock college SSO + lightweight HMAC token (no extra deps)."""
import base64
import hashlib
import hmac
import json
import time
from .config import JWT_SECRET, JWT_TTL_S


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def create_token(sub: str, role: str) -> str:
    header = _b64e(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64e(json.dumps(
        {"sub": sub, "role": role, "exp": int(time.time()) + JWT_TTL_S}
    ).encode())
    sig = _b64e(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(),
                         hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify_token(token: str):
    try:
        header, payload, sig = token.split(".")
        expect = _b64e(hmac.new(JWT_SECRET.encode(), f"{header}.{payload}".encode(),
                                hashlib.sha256).digest())
        if not hmac.compare_digest(expect, sig):
            return None
        data = json.loads(_b64d(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def classify_login(username: str, role_hint: str) -> str:
    u = (username or "").strip()
    hint = (role_hint or "").lower()
    if hint == "admin" or u.lower().startswith("admin") or "teacher" in u.lower():
        return "admin"
    return "student"
