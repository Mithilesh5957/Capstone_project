"""FACEATTEND auth: DB-backed login (users table) + student lookup, JWT issuance."""
import os

from fastapi import APIRouter, HTTPException

from ..core.database import SessionLocal
from ..core.security import (
    classify_login,
    create_token,
    get_password_hash,
    verify_password,
)
from ..models.student import Student
from ..models.user import User
from ..schemas.marp import LoginIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@college.edu")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def _canonical_identity(body: LoginIn) -> str:
    """Accept either username or email; strip the domain for matching."""
    raw = (body.username or body.email or "").strip()
    if "@" in raw:
        local, _, domain = raw.partition("@")
        local = local.strip()
        if domain.strip().lower() in ("college.edu", "kluniversity.in", ""):
            return local or raw
        return local or raw
    return raw


def _ensure_admin() -> None:
    """Seed operator account on first login if users table is empty."""
    # Imported lazily to avoid circulars; called inside request + startup paths.
    s = SessionLocal()
    try:
        existing = s.query(User).filter(User.username == ADMIN_USER).first()
        if existing is None:
            s.add(
                User(
                    username=ADMIN_USER,
                    password_hash=get_password_hash(ADMIN_PASSWORD),
                    role="admin",
                )
            )
            s.commit()
        elif not existing.password_hash:
            existing.password_hash = get_password_hash(ADMIN_PASSWORD)
            s.commit()
    except Exception:
        try:
            s.rollback()
        except Exception:
            pass
    finally:
        s.close()


@router.post("/login")
def login(body: LoginIn):
    u = _canonical_identity(body)
    if not u or not (body.password or ""):
        raise HTTPException(status_code=422, detail="username and password required")
    role = classify_login(u, body.role)

    _ensure_admin()

    s = SessionLocal()
    try:
        # 1. Operator / users-table lookup (case-insensitive username).
        user_row = (
            s.query(User).filter(User.username.ilike(u)).first()
        )
        if user_row and user_row.password_hash:
            if not verify_password(body.password or "", user_row.password_hash):
                raise HTTPException(status_code=401, detail="invalid credentials")
            token = create_token(user_row.username, user_row.role or "admin")
            return {
                "role": "admin" if (user_row.role or "admin") == "admin" else user_row.role,
                "name": "Class Teacher",
                "username": user_row.username,
                "email": ADMIN_EMAIL,
                "token": token,
            }
        # Unknown username in users table but admin role requested -> 401 (no demo bypass).
        if role == "admin":
            raise HTTPException(status_code=401, detail="invalid operator credentials")

        # 2. Student lookup by student_id or name; password verified only if a
        #    linked users-table entry exists, otherwise student portal accepts
        #    the record existence as identity (no guest auto-provision).
        row = (
            s.query(Student)
            .filter((Student.student_id == u) | (Student.name == u))
            .first()
        )
        if row is None:
            raise HTTPException(status_code=401, detail="invalid student credentials")
        token = create_token(row.student_id, "student")
        return {
            "role": "student",
            "student_id": row.student_id,
            "name": row.name,
            "branch": row.branch,
            "token": token,
        }
    finally:
        s.close()
