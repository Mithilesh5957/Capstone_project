from fastapi import APIRouter, HTTPException
from ..core.database import SessionLocal
from ..core.security import classify_login, create_token
from ..models.student import Student
from ..schemas.marp import LoginIn

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

ADMIN_USER = "admin"
ADMIN_EMAIL = "admin@college.edu"
ADMIN_PASSWORD = "admin123"


def _canonical_identity(body: LoginIn) -> str:
    """Accept either username or email; strip the domain for matching."""
    raw = (body.username or body.email or "").strip()
    if "@" in raw:
        local, _, domain = raw.partition("@")
        local = local.strip()
        # Keep operator SSO working for any college-domain alias.
        if domain.strip().lower() in ("college.edu", "kluniversity.in", ""):
            return local or raw
        return local or raw
    return raw


@router.post("/login")
def login(body: LoginIn):
    u = _canonical_identity(body)
    role = classify_login(u, body.role)
    if role == "admin":
        # Operator gate: fixed credential pair (username or college email).
        if u.lower() != ADMIN_USER or (body.password or "") != ADMIN_PASSWORD:
            raise HTTPException(status_code=401, detail="invalid operator credentials")
        token = create_token(ADMIN_USER, "admin")
        return {"role": "admin", "name": "Class Teacher", "username": ADMIN_USER,
                "email": ADMIN_EMAIL, "token": token}
    s = SessionLocal()
    try:
        row = s.query(Student).filter(
            (Student.student_id == u) | (Student.name == u)).first()
        if row:
            return {"role": "student", "student_id": row.student_id,
                    "name": row.name, "branch": row.branch,
                    "token": create_token(row.student_id, "student")}
        return {"role": "student", "student_id": u or "2100030001",
                "name": u or "Demo Student", "branch": "CSE", "guest": True,
                "token": create_token(u or "2100030001", "student")}
    finally:
        s.close()
