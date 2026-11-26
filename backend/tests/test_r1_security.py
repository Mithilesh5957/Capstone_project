"""FACEATTEND R1 security regression tests (Phase 1A).

Scope: C1 (legacy auth bypass), C2 (default/fallback login), C3 (JWT secret
handling), C4 (passwordless student login), C13 (frontend sends Bearer —
covered by backend 401 contract + report §Frontend), WS auth, startup-secret
validation, and legitimate authorized flows.

Method: real HTTP behavior via FastAPI TestClient against an ISOLATED
PostgreSQL database (faceattend_r1_test). No mocks of the auth layer itself.

IMPORTANT test-env note: the pinned production hasher is bcrypt via
passlib, but passlib 1.7.4 is incompatible with bcrypt>=4.1 hashing at
runtime (raises ValueError on hash). The production code path
(get_password_hash/verify_password) is still fully exercised, but tests
substitute a PBKDF2 KDF via monkeypatch. A dedicated test
(test_production_hasher_scheme_is_bcrypt) asserts the production default
remains bcrypt without hashing. See PHASE_1A_SECURITY_REPORT.md.
"""
import hashlib
import os
import secrets
import sys

import pytest

# ---- isolated test configuration: MUST precede any app import ----
# R1_TEST_DATABASE_URL selects the driver for the environment under test:
#   - venv (psycopg v3):      postgresql+psycopg://postgres@localhost/faceattend_r1_test
#   - prod image (psycopg2):  postgresql://postgres@localhost/faceattend_r1_test
# R7 note: this file is also executed inside the pinned py3.11 container,
# where only psycopg2 is available (requirements.txt); the default URL below
# is overridden via R1_TEST_DATABASE_URL in that harness.
os.environ["ENVIRONMENT"] = "test"
if "R1_TEST_DATABASE_URL" in os.environ:
    # Explicit override wins (the prod image bakes its own DATABASE_URL via
    # Docker ENV, which setdefault would otherwise preserve).
    os.environ["DATABASE_URL"] = os.environ["R1_TEST_DATABASE_URL"]
else:
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://postgres@localhost/faceattend_r1_test",
    )
os.environ["JWT_SECRET"] = "r1-test-secret-0123456789abcdef-0123456789"
os.environ["JWT_TTL_S"] = "3600"
os.environ["ADMIN_USER"] = "admin"
os.environ["ADMIN_PASSWORD"] = "StrongTestPass-2026!"
os.environ["MODEL_LOAD_SECONDS"] = "1"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi.testclient import TestClient  # noqa: E402
from jose import jwt  # noqa: E402

import app.core.config as config  # noqa: E402
import app.core.security as security  # noqa: E402
import app.routers.auth_router as auth_router  # noqa: E402
import app.services.marp_engine as marp  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.models.user import User  # noqa: E402

ADMIN_PW = "StrongTestPass-2026!"
STUDENT_PW = "StudentPass-2026!"
STUDENT_ID = "2100030001"


# ---- fallback KDF: used ONLY when the environment's real bcrypt backend
# is broken (observed: passlib 1.7.4 + bcrypt 5.x on Python 3.14 raises
# ValueError on hash). The fixture below prefers the REAL production hasher
# and records which one ran in HASHER_MODE. ----
HASHER_MODE = "unknown"


def _fake_hash(password: str) -> str:
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 1000)
    return f"pbkdf2$test${salt}${dk.hex()}"


def _fake_verify(plain: str, hashed: str) -> bool:
    try:
        _, _, salt, expect = hashed.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", (plain or "").encode(), salt.encode(), 1000)
        return secrets.compare_digest(dk.hex(), expect)
    except Exception:
        return False


@pytest.fixture()
def hasher(monkeypatch):
    """Use the real production hasher when functional; else PBKDF2 fallback.

    Seeding helpers call auth_router.get_password_hash at call time, so they
    automatically follow whichever implementation is active.
    """
    global HASHER_MODE
    try:
        probe = security.get_password_hash("r1-bcrypt-probe")
        assert security.verify_password("r1-bcrypt-probe", probe)
        assert not security.verify_password("wrong", probe)
        HASHER_MODE = "production-bcrypt"
    except Exception:
        monkeypatch.setattr(security, "get_password_hash", _fake_hash)
        monkeypatch.setattr(security, "verify_password", _fake_verify)
        monkeypatch.setattr(auth_router, "get_password_hash", _fake_hash)
        monkeypatch.setattr(auth_router, "verify_password", _fake_verify)
        HASHER_MODE = "pbkdf2-fallback"


@pytest.fixture()
def db():
    # MARP lifespan/telemetry threads run their own defensive create_all
    # (marp_engine.py:260,382-386). On a fresh database that can race this
    # call (check-then-create on marp_telemetry). Retry once on the duplicate-
    # table race only; any other error still fails loudly.
    # R9: the same first-touch race can surface as IntegrityError
    # (UniqueViolation on pg_type) when a MARP telemetry daemon thread's own
    # create_all (via ENGINE.set_stage -> _log_telemetry_async, e.g. from the
    # marp_ready fixture) wins the in-flight CREATE TABLE. Same race, same
    # retry; anything without "already exists" still fails loudly.
    from sqlalchemy.exc import IntegrityError, OperationalError, \
        ProgrammingError

    try:
        Base.metadata.create_all(bind=engine)
    except (OperationalError, ProgrammingError, IntegrityError) as e:
        # DuplicateTable surfaces as ProgrammingError on psycopg2.
        if "already exists" not in str(getattr(e, "orig", e)):
            raise
        Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        # FK-safe cleanup order.
        from app.models.attendance import AttendanceRecord, AttendanceSession
        from app.models.detection import DetectionEvent
        from app.models.telemetry import MarpTelemetry

        for m in (AttendanceRecord, AttendanceSession, Student, User,
                  DetectionEvent, MarpTelemetry):
            s.query(m).delete()
        s.commit()
        yield s
    finally:
        s.close()


@pytest.fixture()
def marp_ready(monkeypatch):
    # R2 widened start_background_load() with an optional reason argument
    # (backward-compatible default); the no-op shim accepts it.
    monkeypatch.setattr(marp, "start_background_load", lambda *a, **k: None)
    # R2 lifespan teardown marks process shutdown globally; the R1 suite
    # models a running app, so each test starts from a non-shutdown state.
    marp._shutdown_event.clear()
    marp.state.update({"phase": "ready", "model_ready": True, "db_ready": True})
    marp.SIMULATED_DB_FAILURE = False
    marp.SIMULATED_MODEL_FAILURE = False
    marp.chaos_knobs.update({k: v for k, v in config.CHAOS_DEFAULTS.items()})
    marp.active_session.update({"id": None, "name": None})
    marp.marked_memory.clear()
    marp.ENGINE.set_stage("READY", "ready")
    yield marp


@pytest.fixture()
def client(marp_ready, db):
    # NOTE: `db` must precede TestClient setup. Entering the app lifespan
    # spawns MARP telemetry threads that run create_all themselves; creating
    # the schema first removes a real check-then-create race that surfaced as
    # a transient DuplicateTable error on the first test of a fresh database.
    with TestClient(app) as c:
        yield c


def _seed_admin(password: str = ADMIN_PW):
    # Uses auth_router.get_password_hash at call time so the active hasher
    # (real bcrypt or PBKDF2 fallback, per the `hasher` fixture) is used.
    s = SessionLocal()
    try:
        if s.query(User).filter(User.username == "admin").first() is None:
            s.add(User(username="admin",
                       password_hash=auth_router.get_password_hash(password),
                       role="admin"))
            s.commit()
    finally:
        s.close()


def _seed_user(username: str, password: str, role: str):
    s = SessionLocal()
    try:
        if s.query(User).filter(User.username == username).first() is None:
            s.add(User(username=username,
                       password_hash=auth_router.get_password_hash(password),
                       role=role))
            s.commit()
    finally:
        s.close()


def _seed_student_record():
    s = SessionLocal()
    try:
        s.add(Student(student_id=STUDENT_ID, name="Test Student", branch="CSE",
                      embeddings=[0.0] * 4096))
        s.commit()
    finally:
        s.close()


def _login(client, username, password, role="admin"):
    return client.post("/api/v1/auth/login",
                       json={"username": username, "password": password, "role": role})


def _admin_headers(client):
    _seed_admin()
    r = _login(client, "admin", ADMIN_PW, "admin")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


# ================= T1: unauthenticated requests rejected =================
PROTECTED_ROUTES = [
    ("POST", "/api/students/enroll"),
    ("GET", "/api/students"),
    ("GET", f"/api/students/{STUDENT_ID}/attendance"),
    ("POST", "/api/detect"),
    ("POST", "/api/detect/annotated"),
    ("POST", "/api/attendance/start"),
    ("POST", "/api/attendance/stop"),
    ("GET", "/api/attendance/roster"),
    ("GET", "/api/attendance/sessions"),
    ("POST", "/api/attendance/override"),
    ("GET", "/api/logs"),
    ("GET", "/api/status"),
    ("POST", "/api/chaos"),
    ("POST", "/api/chaos/db-drop"),
    ("POST", "/api/chaos/unload-model"),
    ("POST", "/api/chaos/recover"),
    ("POST", "/api/v1/students/enroll"),
    ("GET", "/api/v1/students"),
    ("GET", f"/api/v1/students/{STUDENT_ID}/attendance"),
    ("POST", "/api/v1/attendance/start"),
    ("POST", "/api/v1/attendance/stop"),
    ("GET", "/api/v1/attendance/roster"),
    ("GET", "/api/v1/attendance/sessions"),
    ("GET", "/api/v1/attendance/export.csv"),
    ("POST", "/api/v1/attendance/override"),
    ("POST", "/api/v1/attendance/detect"),
    ("POST", "/api/v1/attendance/detect/annotated"),
    ("POST", "/api/v1/marp/chaos"),
    ("POST", "/api/v1/marp/chaos/db-drop"),
    ("POST", "/api/v1/marp/chaos/unload-model"),
    ("POST", "/api/v1/marp/chaos/recover"),
    ("POST", "/api/v1/marp/chaos/inject"),
    ("POST", "/api/v1/marp/chaos/reset"),
    ("POST", "/api/v1/marp/chaos/tune"),
    ("GET", "/api/v1/marp/telemetry/export"),
    ("GET", "/api/v1/marp/status"),
    ("GET", "/api/v1/marp/chaos/status"),
    ("GET", "/api/v1/settings/detection"),
    ("POST", "/api/v1/settings/detection"),
    ("POST", "/api/v1/auth/provision-student"),
]

_OPEN_ROUTES = [
    ("GET", "/healthz/liveness"),
    ("GET", "/healthz/readiness"),
    ("GET", "/api/v1/marp/healthz/liveness"),
    ("GET", "/api/v1/marp/healthz/readiness"),
]


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_unauthenticated_protected_routes_rejected(client, db, hasher, method, path):
    body: dict = {}
    if path.endswith("/start"):
        body = {"session_name": "R1 probe"}
    elif path.endswith("/override"):
        body = {"session_id": 1, "student_id": STUDENT_ID, "status": "Present"}
    elif path.endswith("/enroll"):
        body = {"student_id": "x", "name": "x", "images": []}
    elif path.endswith("/chaos"):
        body = {"failure": "db_drop"}
    elif path.endswith("/inject"):
        body = {"simulated_latency_sec": 0.0, "frame_drop_rate": 0.0,
                "simulate_vram_exhaustion": False,
                "artificial_probe_failure": False, "model_stall": False}
    elif path.endswith("/provision-student"):
        body = {"student_id": STUDENT_ID, "password": STUDENT_PW}
    elif path.endswith("/detect") or path.endswith("/annotated"):
        body = {"image": ""}
    r = client.request(method, path, json=body if method == "POST" else None)
    assert r.status_code in (401, 403, 422), f"{method} {path} -> {r.status_code}: {r.text}"
    # 422 is only acceptable for schema-level body validation AFTER auth;
    # unauthenticated requests must never succeed.
    assert r.status_code != 200, f"{method} {path} unexpectedly authorized"


@pytest.mark.parametrize("method,path", _OPEN_ROUTES)
def test_public_probes_stay_open(client, db, method, path):
    r = client.request(method, path)
    assert r.status_code == 200, f"{method} {path} -> {r.status_code}"


# ================= T2: insufficient privilege =================
def test_student_token_forbidden_on_admin_routes(client, db, hasher):
    _seed_admin()
    _seed_student_record()
    _seed_user(STUDENT_ID, STUDENT_PW, "student")
    r = _login(client, STUDENT_ID, STUDENT_PW, "student")
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    for method, path in [("POST", "/api/v1/attendance/start"),
                         ("POST", "/api/students/enroll"),
                         ("POST", "/api/v1/marp/chaos/db-drop"),
                         ("GET", "/api/v1/students"),
                         ("GET", "/api/v1/attendance/roster"),
                         ("POST", "/api/attendance/start")]:
        body = {"session_name": "x"} if path.endswith("/start") else (
            {"student_id": "x", "name": "x", "images": []} if path.endswith("/enroll") else None)
        resp = client.request(method, path, json=body if method == "POST" else None,
                              headers=h)
        assert resp.status_code == 403, f"{method} {path} -> {resp.status_code}"


def test_student_can_read_own_record_only(client, db, hasher):
    _seed_admin()
    _seed_student_record()
    _seed_user(STUDENT_ID, STUDENT_PW, "student")
    s = SessionLocal()
    try:
        if s.query(Student).filter(Student.student_id == "OTHER1").first() is None:
            s.add(Student(student_id="OTHER1", name="Other", branch="ECE",
                          embeddings=[0.0] * 8))
            s.commit()
    finally:
        s.close()
    tok = _login(client, STUDENT_ID, STUDENT_PW, "student").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"/api/v1/students/{STUDENT_ID}/attendance",
                      headers=h).status_code == 200
    r = client.get("/api/v1/students/OTHER1/attendance", headers=h)
    assert r.status_code == 403, r.text


# ================= T3: forged / expired / malformed tokens =================
def test_forged_expired_malformed_tokens_rejected(client, db, hasher):
    forged = jwt.encode({"sub": "admin", "role": "admin"}, "wrong-secret",
                        algorithm="HS256")
    expired = security.create_token("admin", "admin", expires_s=-10)
    for bad in [forged, expired, "not-a-jwt", ""]:
        r = client.get("/api/v1/attendance/roster",
                       headers={"Authorization": f"Bearer {bad}"})
        assert r.status_code == 401, f"token={bad[:12]!r} -> {r.status_code}"


# ================= T4/T5: login matrix =================
def test_admin_login_success_and_password_verified(client, db, hasher):
    _seed_admin()
    ok = _login(client, "admin", ADMIN_PW, "admin")
    assert ok.status_code == 200, ok.text
    assert ok.json()["token"]
    payload = security.verify_token(ok.json()["token"])
    assert payload["role"] == "admin"
    bad = _login(client, "admin", "wrong-password", "admin")
    assert bad.status_code == 401, bad.text
    unknown = _login(client, "nosuchop", "whatever", "admin")
    assert unknown.status_code == 401, unknown.text


def test_student_login_matrix(client, db, hasher):
    _seed_admin()
    # Unknown student -> 401.
    assert _login(client, "UNKNOWN9", "pw", "student").status_code == 401
    _seed_student_record()
    # Known but NOT provisioned -> 401 (R1: no passwordless JWT).
    r = _login(client, STUDENT_ID, "anything", "student")
    assert r.status_code == 401, r.text
    assert "provision" in r.json()["detail"].lower()
    # Provision then wrong password -> 401.
    admin_h = _admin_headers(client)
    pv = client.post("/api/v1/auth/provision-student",
                     json={"student_id": STUDENT_ID, "password": STUDENT_PW},
                     headers=admin_h)
    assert pv.status_code == 200, pv.text
    assert _login(client, STUDENT_ID, "wrong", "student").status_code == 401
    # Correct password -> 200 with student token.
    good = _login(client, STUDENT_ID, STUDENT_PW, "student")
    assert good.status_code == 200, good.text
    assert security.verify_token(good.json()["token"])["role"] == "student"
    # Provisioning an unknown student -> 404; unauthenticated -> 401.
    assert client.post("/api/v1/auth/provision-student",
                       json={"student_id": "NOPE", "password": STUDENT_PW},
                       headers=admin_h).status_code == 404
    assert client.post("/api/v1/auth/provision-student",
                       json={"student_id": STUDENT_ID,
                             "password": STUDENT_PW}).status_code == 401


def test_production_bootstrap_fails_closed(client, db, hasher, monkeypatch):
    monkeypatch.setattr(config, "is_production", lambda: True)
    monkeypatch.setattr(auth_router, "is_production", lambda: True)
    monkeypatch.setattr(auth_router, "ADMIN_PASSWORD", "")
    r = _login(client, "admin", "anything", "admin")
    assert r.status_code == 503, r.text


# ================= T7: websocket auth =================
def test_websocket_auth(marp_ready, db, hasher):
    from starlette.websockets import WebSocketDisconnect

    _seed_admin()
    _seed_student_record()
    _seed_user(STUDENT_ID, STUDENT_PW, "student")
    with TestClient(app) as ws_client:
        admin_tok = _login(ws_client, "admin", ADMIN_PW, "admin").json()["token"]
        student_tok = _login(ws_client, STUDENT_ID, STUDENT_PW,
                             "student").json()["token"]
        # No token -> 4401 on both legacy and v1 sockets. Note: the server
        # accepts first, then closes — so the close surfaces on receive.
        for path in ("/ws/detect", "/api/v1/attendance/ws/detect"):
            with ws_client.websocket_connect(path) as ws:
                try:
                    ws.receive_json()
                    pytest.fail(f"{path} accepted anonymous socket")
                except WebSocketDisconnect as e:
                    assert e.code == 4401, f"{path} -> {e.code}"
        # Student token on marking socket -> 4403 (operator role required).
        with ws_client.websocket_connect(
                f"/ws/detect?token={student_tok}") as ws:
            try:
                ws.receive_json()
                pytest.fail("student socket accepted on marking WS")
            except WebSocketDisconnect as e:
                assert e.code == 4403, f"student ws -> {e.code}"
        # Admin token -> accepted; empty frame yields error envelope (no CV).
        with ws_client.websocket_connect(f"/ws/detect?token={admin_tok}") as ws:
            ws.send_json({"image": ""})
            msg = ws.receive_json()
            assert "detections" in msg


# ================= T9: legitimate authorized flows =================
def test_authorized_session_lifecycle(client, db, hasher, monkeypatch):
    import app.routers.students_router as students_router
    import app.services.face_detection as fd_mod
    import app.services.face_recognition as fr_mod
    import numpy as np

    monkeypatch.setattr(fd_mod, "decode_frame",
                        lambda b64: np.zeros((480, 640, 3), dtype=np.uint8))
    monkeypatch.setattr(fr_mod, "embedding_from_bytes",
                        lambda raw: [0.1] * 4096)
    h = _admin_headers(client)
    fake_img = "dGVzdA=="  # base64("test"); CV is stubbed above
    # Enroll via v1 AND legacy with admin token.
    for url in ("/api/v1/students/enroll", "/api/students/enroll"):
        r = client.post(url, json={"student_id": STUDENT_ID, "name": "Test Student",
                                   "branch": "CSE",
                                   "images": [fake_img] * 4}, headers=h)
        assert r.status_code == 200, f"{url} -> {r.status_code}: {r.text}"
        assert r.json()["embedding_dim"] == 4096
    # Session lifecycle.
    st = client.post("/api/v1/attendance/start", json={"session_name": "R1"},
                     headers=h)
    assert st.status_code == 200, st.text
    sid = st.json()["session_id"]
    roster = client.get(f"/api/v1/attendance/roster?session_id={sid}", headers=h)
    assert roster.status_code == 200
    assert any(rec["student_id"] == STUDENT_ID for rec in roster.json()["records"])
    ov = client.post("/api/v1/attendance/override",
                     json={"session_id": sid, "student_id": STUDENT_ID,
                           "status": "Present"}, headers=h)
    assert ov.status_code == 200, ov.text
    # Model-loading gate still honest: 503 when not ready (with auth passing).
    marp.state["model_ready"] = False
    r503 = client.post("/api/v1/students/enroll",
                       json={"student_id": "N", "name": "N",
                             "images": [fake_img]}, headers=h)
    assert r503.status_code == 503, r503.text
    marp.state["model_ready"] = True


def test_admin_logs_and_export_require_admin(client, db, hasher):
    h = _admin_headers(client)
    assert client.get("/api/logs", headers=h).status_code == 200
    assert client.get("/api/v1/attendance/export.csv?session_id=1",
                      headers=h).status_code in (200, 404, 500)


# ================= T8/T10: secrets =================
def test_startup_secret_validation(monkeypatch):
    # validate_startup_secrets reads secrets from the environment at call
    # time; only the ENVIRONMENT switch (module global) needs patching, so
    # no module reload is required (a reload would desync other modules'
    # reference to the config object).
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    for secret, pw in [("", ""), ("short", "short"),
                       ("faceattend-dev-secret", "admin123"),
                       ("default_dev_secret_change_me", "StrongTestPass-2026!"),
                       ("a-very-long-test-secret-0123456789abcdef", "admin123")]:
        monkeypatch.setenv("JWT_SECRET", secret)
        monkeypatch.setenv("ADMIN_PASSWORD", pw)
        with pytest.raises(RuntimeError):
            config.validate_startup_secrets()
    monkeypatch.setenv("JWT_SECRET", "a-very-long-test-secret-0123456789abcdef")
    monkeypatch.setenv("ADMIN_PASSWORD", "StrongTestPass-2026!")
    config.validate_startup_secrets()  # must not raise


def test_production_lifespan_refuses_weak_secrets(marp_ready, db, monkeypatch):
    # Full startup path (not just the validator in isolation): with
    # ENVIRONMENT=production and documented defaults, entering the app
    # lifespan must raise instead of serving traffic.
    monkeypatch.setattr(config, "ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "default_dev_secret_change_me")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin123")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_jwt_secret_single_source():
    assert security.JWT_SECRET == config.JWT_SECRET
    assert len(security.JWT_SECRET) >= 32


def test_production_hasher_scheme_is_bcrypt():
    assert security.pwd_context.schemes() == ("bcrypt",)


def test_hasher_mode_reported(hasher):
    # Documents which KDF the suite actually exercised (see module docstring).
    assert HASHER_MODE in ("production-bcrypt", "pbkdf2-fallback")
    print(f"\n[HASHER_MODE] {HASHER_MODE}")


# ================= T2b: student forbidden on ALL admin mutating routes ====
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/chaos"),
    ("POST", "/api/chaos/recover"),
    ("POST", "/api/v1/marp/chaos"),
    ("POST", "/api/v1/marp/chaos/inject"),
    ("POST", "/api/v1/marp/chaos/reset"),
    ("POST", "/api/v1/marp/chaos/tune"),
    ("POST", "/api/v1/marp/chaos/unload-model"),
    ("POST", "/api/v1/marp/chaos/recover"),
    ("POST", "/api/v1/auth/provision-student"),
    ("POST", "/api/v1/attendance/detect"),
    ("POST", "/api/attendance/override"),
    ("GET", "/api/v1/attendance/export.csv"),
    ("GET", "/api/v1/marp/telemetry/export"),
    ("GET", "/api/logs"),
    ("POST", "/api/v1/settings/detection"),
])
def test_student_token_forbidden_everywhere(client, db, hasher, method, path):
    _seed_admin()
    _seed_student_record()
    _seed_user(STUDENT_ID, STUDENT_PW, "student")
    tok = _login(client, STUDENT_ID, STUDENT_PW, "student").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    body: dict = {}
    if path.endswith("/override"):
        body = {"session_id": 1, "student_id": STUDENT_ID, "status": "Present"}
    elif path.endswith("/provision-student"):
        body = {"student_id": STUDENT_ID, "password": STUDENT_PW}
    elif path.endswith("/detect"):
        body = {"image": ""}
    elif path.endswith("/inject"):
        body = {"simulated_latency_sec": 0.0, "frame_drop_rate": 0.0,
                "simulate_vram_exhaustion": False,
                "artificial_probe_failure": False, "model_stall": False}
    r = client.request(method, path, json=body if method == "POST" else None,
                       headers=h)
    assert r.status_code == 403, f"{method} {path} -> {r.status_code}: {r.text}"


# ================= T5b: provisioning cannot hijack other identities ========
def test_provision_cannot_overwrite_admin_identity(client, db, hasher):
    admin_h = _admin_headers(client)
    # "admin" is not a student record, and even if it were, the operator
    # identity must never be merged into a student credential.
    r = client.post("/api/v1/auth/provision-student",
                    json={"student_id": "admin", "password": "SomePass-123"},
                    headers=admin_h)
    assert r.status_code in (404, 409), r.text
    # Operator credential still verifies with the ORIGINAL password.
    ok = _login(client, "admin", ADMIN_PW, "admin")
    assert ok.status_code == 200, ok.text
    assert security.verify_token(ok.json()["token"])["role"] == "admin"


def test_ensure_admin_never_overwrites_hash(client, db, hasher):
    _seed_admin("Original-Admin-Pass-1")
    # A login triggers _ensure_admin(); the stored hash must be untouched.
    before = SessionLocal().query(User).filter(
        User.username == "admin").first().password_hash
    assert _login(client, "admin", "Original-Admin-Pass-1",
                  "admin").status_code == 200
    after = SessionLocal().query(User).filter(
        User.username == "admin").first().password_hash
    assert before == after


def test_admin_username_like_student_gets_db_role(client, db, hasher):
    # A student_id starting with "admin" classifies as operator by name, but
    # the issued role must come from the provisioned DB row (least privilege).
    tricky = "admincadet1"
    _seed_admin()
    s = SessionLocal()
    try:
        s.add(Student(student_id=tricky, name="Admin Cadet", branch="CSE",
                      embeddings=[]))
        s.commit()
    finally:
        s.close()
    admin_h = _admin_headers(client)
    assert client.post("/api/v1/auth/provision-student",
                       json={"student_id": tricky, "password": STUDENT_PW},
                       headers=admin_h).status_code == 200
    r = _login(client, tricky, STUDENT_PW, "student")
    assert r.status_code == 200, r.text
    assert security.verify_token(r.json()["token"])["role"] == "student"


def test_student_can_read_transparency_endpoints(client, db, hasher):
    # Intended policy (per PHASE_1A report): operational transparency
    # endpoints (status, detection config view) are any-authenticated;
    # mutations stay admin-only (covered above).
    _seed_admin()
    _seed_student_record()
    _seed_user(STUDENT_ID, STUDENT_PW, "student")
    tok = _login(client, STUDENT_ID, STUDENT_PW, "student").json()["token"]
    h = {"Authorization": f"Bearer {tok}"}
    for path in ("/api/v1/marp/status", "/api/v1/marp/chaos/status",
                 "/api/v1/settings/detection"):
        r = client.get(path, headers=h)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text}"


def test_admin_can_read_any_student_record(client, db, hasher):
    _seed_admin()
    _seed_student_record()
    admin_h = _admin_headers(client)
    r = client.get(f"/api/v1/students/{STUDENT_ID}/attendance", headers=admin_h)
    assert r.status_code == 200, r.text
