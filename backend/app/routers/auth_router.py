"""FACEATTEND auth: DB-backed login (users table) + student lookup, JWT issuance.

R1 security policy:
- Operator login always verifies a bcrypt password hash from the users table.
- Student login verifies a password against a provisioned users-table row
  (username == student_id, role == "student"). Knowing a student_id alone
  never yields a token. Use POST /provision-student (admin) to provision.
- No default credentials are seeded in production. In non-production, a dev
  admin is seeded from ADMIN_USER/ADMIN_PASSWORD env with a stderr warning.
"""
import os
import sys

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.config import (
    INSECURE_ADMIN_PASSWORDS,
    MIN_ADMIN_PASSWORD_LEN,
    is_production,
)
from ..core.database import SessionLocal
from ..core.security import (
    classify_login,
    create_token,
    get_password_hash,
    require_admin,
    verify_password,
)
from ..models.student import Student
from ..models.user import User
from ..schemas.marp import LoginIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@college.edu")
# No insecure default: production must export ADMIN_PASSWORD explicitly.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")


class ProvisionStudentIn(BaseModel):
    student_id: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=8, max_length=128)


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
    """Bootstrap the operator account when the users table is empty.

    - Non-production: seed ADMIN_USER from ADMIN_PASSWORD env (dev default
      only when ADMIN_PASSWORD is explicitly set); warn on stderr. Never
      overwrites an existing hash.
    - Production: seed ONLY when ADMIN_PASSWORD env is strong (>=
      MIN_ADMIN_PASSWORD_LEN and not a known default). Otherwise leave the
      table empty so login fails closed with 503 "admin not provisioned"
      (startup validation in lifespan rejects this configuration first).
    """
    desired = (ADMIN_PASSWORD or "").strip()
    if not desired:
        if is_production():
            return  # fail closed; login reports "admin not provisioned"
        desired = "admin123"
        print(
            "[faceattend] WARNING: ADMIN_PASSWORD not set; using dev-only "
            "bootstrap credential. Never use this in production.",
            file=sys.stderr,
        )
    elif desired in INSECURE_ADMIN_PASSWORDS or len(desired) < MIN_ADMIN_PASSWORD_LEN:
        if is_production():
            return  # fail closed; startup validation rejects this config
        print(
            "[faceattend] WARNING: ADMIN_PASSWORD is weak; dev-only bootstrap. "
            "Use a strong password in production.",
            file=sys.stderr,
        )
    s = SessionLocal()
    try:
        existing = s.query(User).filter(User.username == ADMIN_USER).first()
        if existing is None:
            s.add(
                User(
                    username=ADMIN_USER,
                    password_hash=get_password_hash(desired),
                    role="admin",
                )
            )
            s.commit()
        # Never overwrite an existing hash from env (avoids lockout/rotation
        # surprises and avoids re-seeding a compromised default).
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
        if user_row is None and role == "admin":
            admins = s.query(User).filter(User.role == "admin").count()
            if admins == 0:
                raise HTTPException(
                    status_code=503,
                    detail="admin account not provisioned; set a strong "
                    "ADMIN_PASSWORD and restart",
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

        # 2. Student login: a provisioned users-table row
        #    (username == student_id, role == "student") is REQUIRED and the
        #    password is always verified. Record existence alone never yields
        #    a token (R1 fix for passwordless student JWT issuance).
        student_row = (
            s.query(Student)
            .filter((Student.student_id == u) | (Student.name == u))
            .first()
        )
        if student_row is None:
            raise HTTPException(status_code=401, detail="invalid student credentials")
        login_id = student_row.student_id
        cred = (
            s.query(User)
            .filter(User.username == login_id, User.role == "student")
            .first()
        )
        if cred is None or not cred.password_hash:
            raise HTTPException(
                status_code=401,
                detail="student login not provisioned; contact administrator",
            )
        if not verify_password(body.password or "", cred.password_hash):
            raise HTTPException(status_code=401, detail="invalid student credentials")
        token = create_token(login_id, "student")
        return {
            "role": "student",
            "student_id": login_id,
            "name": student_row.name,
            "branch": student_row.branch,
            "token": token,
        }
    finally:
        s.close()


@router.post("/provision-student")
def provision_student(body: ProvisionStudentIn, _admin: dict = Depends(require_admin)):
    """Provision (or rotate) a student portal password (admin only).

    Backward-compatible: no schema change — credentials live in the existing
    ``users`` table (username == student_id, role == "student"). Requires the
    student record to already exist (created via enrollment).
    """
    sid = (body.student_id or "").strip()
    s = SessionLocal()
    try:
        row = s.query(Student).filter(Student.student_id == sid).first()
        if row is None:
            raise HTTPException(status_code=404, detail="unknown student_id")
        other = (
            s.query(User)
            .filter(User.username == sid, User.role != "student")
            .first()
        )
        if other is not None:
            # Fail closed: never merge into / overwrite a non-student identity
            # (e.g. the operator account). Previously this fell through to an
            # INSERT that violated UNIQUE(username) and returned a 500.
            raise HTTPException(
                status_code=409,
                detail="username already provisioned with a different role",
            )
        cred = (
            s.query(User)
            .filter(User.username == sid, User.role == "student")
            .first()
        )
        if cred is None:
            s.add(
                User(
                    username=sid,
                    password_hash=get_password_hash(body.password),
                    role="student",
                )
            )
        else:
            cred.password_hash = get_password_hash(body.password)
        s.commit()
        return {"ok": True, "student_id": sid}
    except HTTPException:
        raise
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"provisioning failed: {e}")
    finally:
        s.close()
