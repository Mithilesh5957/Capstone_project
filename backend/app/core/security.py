"""FACEATTEND auth core: bcrypt hashing + JWT (python-jose) + FastAPI guards.

Secrets are env-driven with a secure dev fallback. Production MUST set JWT_SECRET.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from .config import JWT_ALG, JWT_SECRET, JWT_TTL_S

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_token(sub: str, role: str, expires_s: int | None = None) -> str:
    ttl = expires_s if expires_s is not None else JWT_TTL_S
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def verify_token(token: str):
    """Return payload dict or None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError:
        return None


def classify_login(username: str, role_hint: str) -> str:
    u = (username or "").strip()
    hint = (role_hint or "").lower()
    if hint == "admin" or u.lower().startswith("admin") or "teacher" in u.lower():
        return "admin"
    return "student"


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
):
    """FastAPI dependency: validates `Authorization: Bearer <JWT>`."""
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = verify_token(creds.credentials)
    if payload is None or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {"sub": payload.get("sub"), "role": payload.get("role", "")}


def require_admin(user: dict = Depends(get_current_user)):
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="operator privileges required")
    return user


# Authenticated (any role) — for endpoints that need a valid login but no
# operator privilege. Distinct name so route policies read explicitly.
require_authenticated = get_current_user


def enforce_self_or_admin(target_student_id: str, user: dict) -> dict:
    """Least-privilege rule for per-student records.

    Admins may view any student; students may view only their own record
    (``sub`` of a student JWT is the student_id).
    """
    if user.get("role") == "admin":
        return user
    if user.get("role") == "student" and user.get("sub") == (target_student_id or "").strip():
        return user
    raise HTTPException(status_code=403, detail="access limited to own record")
