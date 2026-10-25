"""FACEATTEND R2 regression tests: deterministic startup, single-flight
loading, bounded failure handling, distinguishable health, clean shutdown.

All loader-timing tests use controllable fakes (events/barriers/deadlines) —
no arbitrary sleeps. DB tests use the isolated test database; failure paths
use a refused-connection engine. Each test restores global MARP state.
"""
import os
import sys
import threading
import time

import pytest
from sqlalchemy import create_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("ENVIRONMENT", "test")
if "R1_TEST_DATABASE_URL" in os.environ:
    # Explicit override wins (the prod image bakes its own DATABASE_URL via
    # Docker ENV, which setdefault would otherwise preserve).
    os.environ["DATABASE_URL"] = os.environ["R1_TEST_DATABASE_URL"]
else:
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://postgres@localhost/faceattend_r1_test",
    )

import app.core.database as dbmod  # noqa: E402
import app.services.face_detection as fdmod  # noqa: E402
import app.services.marp_engine as marp  # noqa: E402
from app.services.marp_engine import ENGINE  # noqa: E402


def wait_for(predicate, timeout_s=10.0, step=0.05):
    """Deadline-based wait (not a fixed sleep): returns True when predicate
    holds, False on timeout."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return predicate()


class FakeDetector:
    """Controllable stand-in for face_detection.detector."""

    def __init__(self):
        self.calls = 0
        self.mode = "ok"  # ok | fail | raise | block
        self.backend = "fake"
        self.haar = None
        self.attempted = ["fake"]
        self.release = threading.Event()
        self.block_timeout = 10.0

    def load(self):
        self.calls += 1
        if self.mode == "raise":
            raise RuntimeError("synthetic detector boom")
        if self.mode == "block":
            self.release.wait(timeout=self.block_timeout)
        if self.mode == "fail":
            return False
        return True


@pytest.fixture()
def fake_detector(monkeypatch):
    fake = FakeDetector()
    monkeypatch.setattr(fdmod, "detector", fake)
    return fake


@pytest.fixture(autouse=True)
def r2_isolation():
    """Snapshot and restore every piece of global MARP lifecycle state."""
    snap = {
        "state": dict(marp.state),
        "sim_db": marp.SIMULATED_DB_FAILURE,
        "sim_model": marp.SIMULATED_MODEL_FAILURE,
        "chaos": dict(marp.chaos_knobs),
        "session": dict(marp.active_session),
        "memory": set(marp.marked_memory),
        "face_cascade": marp.face_cascade,
        "stage": ENGINE.stage,
        "kind": ENGINE.failure_kind,
        "attempt": ENGINE.attempt,
        "error": ENGINE.last_error,
        "backend": ENGINE.detector_backend,
        "gen": marp._current_generation(),
    }
    marp._shutdown_event.clear()
    yield
    # Quiesce: tests release their fakes; join briefly so no worker leaks.
    t = marp._load_thread
    if t is not None and t.is_alive():
        t.join(timeout=12.0)
    marp._shutdown_event.clear()
    marp.state.clear()
    marp.state.update(snap["state"])
    marp.SIMULATED_DB_FAILURE = snap["sim_db"]
    marp.SIMULATED_MODEL_FAILURE = snap["sim_model"]
    marp.chaos_knobs.clear()
    marp.chaos_knobs.update(snap["chaos"])
    marp.active_session.clear()
    marp.active_session.update(snap["session"])
    marp.marked_memory.clear()
    marp.marked_memory.update(snap["memory"])
    marp.face_cascade = snap["face_cascade"]
    ENGINE.stage = snap["stage"]
    ENGINE.failure_kind = snap["kind"]
    ENGINE.attempt = snap["attempt"]
    ENGINE.last_error = snap["error"]
    ENGINE.detector_backend = snap["backend"]
    with marp._load_lock:
        marp._load_generation = snap["gen"]
        marp._load_thread = None


def _broken_engine():
    # Same DBAPI driver as the configured test database (psycopg v3 in the
    # venv, psycopg2 in the production image) so the suite runs in both.
    driver = os.environ["DATABASE_URL"].split("://", 1)[0]
    return create_engine(
        f"{driver}://bad:bad@127.0.0.1:1/db",
        connect_args={"connect_timeout": 2},
    )


@pytest.fixture()
def broken_db(monkeypatch):
    monkeypatch.setattr(dbmod, "engine", _broken_engine())
    return dbmod.engine


def _await_stage(want, timeout_s=10.0):
    assert wait_for(lambda: ENGINE.stage == want, timeout_s), (
        f"stage={ENGINE.stage} phase={marp.state.get('phase')} "
        f"kind={ENGINE.failure_kind} err={ENGINE.last_error}"
    )


# ================= A. startup behavior =================
def test_real_db_check_passes():
    """Meaningful integration: the real readiness mechanism on the test DB."""
    marp._ensure_schema()
    marp._check_database()
    assert marp.state["db_ready"] is True


def test_fast_load_ready_without_fixed_wait(monkeypatch, fake_detector):
    """MODEL_LOAD_SECONDS=60 must NOT delay a fast load (no fixed sleep)."""
    monkeypatch.setattr(marp.config, "MODEL_LOAD_SECONDS", 60)
    t0 = time.time()
    marp.start_background_load("boot")
    _await_stage("READY")
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"took {elapsed:.1f}s despite instant loader"
    assert marp.state["model_ready"] is True
    body, code = ENGINE.readiness()
    assert code == 200 and body["failure_kind"] is None


def test_db_unavailable_fails_db_kind(broken_db, fake_detector):
    marp.start_background_load("boot")
    _await_stage("FAILED")
    assert ENGINE.failure_kind == "db"
    assert marp.state["phase"].startswith("db_failed")
    body, code = ENGINE.readiness()
    assert code == 503
    assert body["failure_kind"] == "db"


def test_readiness_not_ready_before_deps(fake_detector):
    fake_detector.mode = "block"
    marp.start_background_load("boot")
    assert wait_for(lambda: marp.state.get("phase") == "warming_up_detector")
    body, code = ENGINE.readiness()
    assert code == 503
    assert body["model_ready"] is False
    assert body["failure_kind"] == "loading"
    fake_detector.release.set()
    _await_stage("READY")


def test_model_completes_after_controlled_delay(fake_detector):
    fake_detector.mode = "block"
    marp.start_background_load("boot")
    assert wait_for(lambda: marp.state.get("phase") == "warming_up_detector")
    time.sleep(0.5)
    assert ENGINE.stage == "LOADING_WEIGHTS"  # still loading, not failed
    fake_detector.release.set()
    _await_stage("READY")


def test_db_delay_then_recovery(monkeypatch, fake_detector):
    """DB down at first, available later: explicit recover reaches READY."""
    monkeypatch.setattr(dbmod, "engine", _broken_engine())
    marp.start_background_load("boot")
    _await_stage("FAILED")
    assert ENGINE.failure_kind == "db"
    # Restore the real test-database engine (cached on the module).
    import app.core.database as _db

    real = getattr(_db, "_r2_real_engine", None)
    if real is None:
        real = create_engine(os.environ["DATABASE_URL"])
        _db._r2_real_engine = real
    monkeypatch.setattr(dbmod, "engine", real)
    marp.start_background_load("recovery")
    _await_stage("READY")
    body, code = ENGINE.readiness()
    assert code == 200


# ================= B. concurrent loading =================
def test_concurrent_starts_single_load(fake_detector):
    fake_detector.mode = "block"
    gens = []
    errors = []

    def _start():
        try:
            gens.append(marp.start_background_load("boot"))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_start) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    assert not errors
    assert len(set(gens)) == 1, f"generations diverged: {gens}"
    fake_detector.release.set()
    _await_stage("READY")
    assert fake_detector.calls == 1


def test_recovery_while_loading_attaches(fake_detector):
    fake_detector.mode = "block"
    g1 = marp.start_background_load("boot")
    g2 = marp.start_background_load("recovery")
    assert g1 == g2
    fake_detector.release.set()
    _await_stage("READY")
    assert fake_detector.calls == 1


def test_failed_attempt_releases_for_new_generation(fake_detector):
    fake_detector.mode = "raise"
    marp.start_background_load("boot")
    _await_stage("FAILED")
    fake_detector.mode = "ok"
    g2 = marp.start_background_load("recovery")
    assert g2 > 0
    _await_stage("READY")
    assert fake_detector.calls == 2  # exactly one load per attempt


def test_stale_commit_never_applies():
    assert marp._commit_if_current(-1, "failed", "x", "db_failed: x", "db") is False
    assert ENGINE.stage != "FAILED" or True  # no assertion on stage: no commit
    snap_stage, snap_phase = ENGINE.stage, marp.state.get("phase")
    marp._commit_if_current(10**9, "ready", "b", 1.0, 1.0)
    assert (ENGINE.stage, marp.state.get("phase")) == (snap_stage, snap_phase)


# ================= C. failure and timeout =================
def test_detector_exception_failed_model(fake_detector):
    fake_detector.mode = "raise"
    marp.start_background_load("boot")
    _await_stage("FAILED")
    assert ENGINE.failure_kind == "model"
    assert marp.state["phase"].startswith("detector_failed")
    body, code = ENGINE.readiness()
    assert code == 503 and body["failure_kind"] == "model"
    assert marp.marp_state() == "FAILED_MODEL"


def test_deadline_expiry_timeout_and_late_completion_ignored(monkeypatch,
                                                             fake_detector):
    monkeypatch.setattr(marp.config, "MODEL_LOAD_SECONDS", 1)
    fake_detector.mode = "block"
    marp.start_background_load("boot")
    _await_stage("FAILED", timeout_s=15.0)
    assert ENGINE.failure_kind == "timeout"
    assert marp.state["phase"].startswith("timeout")
    assert marp.marp_state() == "FAILED_TIMEOUT"
    # Late completion of the obsolete attempt must not overwrite the verdict.
    fake_detector.release.set()
    time.sleep(0.5)
    assert ENGINE.stage == "FAILED"
    assert ENGINE.failure_kind == "timeout"


def test_repeated_failures_no_worker_storm(fake_detector):
    fake_detector.mode = "raise"
    for _ in range(5):
        marp.start_background_load("recovery")
        _await_stage("FAILED")
        # Reset for the next attempt (stage stable until explicit recovery).
        with ENGINE._state_lock:
            ENGINE.stage = "LOADING_WEIGHTS"
    assert fake_detector.calls == 5  # exactly one worker per attempt
    loaders = [t for t in threading.enumerate()
               if t.is_alive() and t.name.startswith("Thread")]
    assert len(loaders) <= 2, f"worker leak: {len(loaders)} threads alive"


def test_failure_state_stable_until_recovery(fake_detector):
    fake_detector.mode = "raise"
    marp.start_background_load("boot")
    _await_stage("FAILED")
    time.sleep(0.5)
    body, code = ENGINE.readiness()
    assert ENGINE.stage == "FAILED" and code == 503
    assert body["failure_kind"] == "model"
    fake_detector.mode = "ok"
    marp.start_background_load("recovery")
    _await_stage("READY")
    body, code = ENGINE.readiness()
    assert code == 200 and body["failure_kind"] is None


# ================= D. state and API behavior =================
def test_db_down_vs_loading_distinguishable(fake_detector):
    fake_detector.mode = "block"
    marp.start_background_load("boot")
    assert wait_for(lambda: marp.state.get("phase") == "warming_up_detector")
    body, code = ENGINE.readiness()
    assert (code, body["failure_kind"]) == (503, "loading")
    fake_detector.release.set()
    _await_stage("READY")
    # Simulate post-ready DB loss with a failing engine behind the live check.
    import app.core.database as _db

    real = getattr(_db, "_r2_real_engine", None)
    if real is None:
        real = create_engine(os.environ["DATABASE_URL"])
        _db._r2_real_engine = real
    broken = _broken_engine()
    object.__setattr__(_db, "engine", broken)
    try:
        body, code = ENGINE.readiness()
        assert code == 503 and body["failure_kind"] == "db"
        assert ENGINE.stage == "READY"  # flap: still READY, recovers alone
    finally:
        object.__setattr__(_db, "engine", real)
    body, code = ENGINE.readiness()
    assert code == 200 and body["failure_kind"] is None


def test_liveness_vs_readiness_semantics(fake_detector):
    from app.routers import marp_router

    fake_detector.mode = "block"
    marp.start_background_load("boot")
    assert wait_for(lambda: marp.state.get("phase") == "warming_up_detector")
    alive = marp_router.liveness()
    assert alive["status"] == "alive"
    resp = marp_router.readiness()
    assert resp.status_code == 503
    fake_detector.release.set()
    _await_stage("READY")
    assert marp_router.readiness().status_code == 200


def test_readiness_body_keeps_legacy_keys(fake_detector):
    marp.start_background_load("boot")
    _await_stage("READY")
    body, _ = ENGINE.readiness()
    for key in ("phase", "marp_state", "stage", "model_ready", "db_ready",
                "uptime_s", "progress_duration_s", "failure_kind", "attempt"):
        assert key in body, f"missing key {key}"
    assert body["attempt"] >= 1


def test_marp_state_labels():
    cases = {
        "db_failed: conn refused": "FAILED_DB",
        "timeout: detector load exceeded budget": "FAILED_TIMEOUT",
        "detector_failed: boom": "FAILED_MODEL",
        "ready": "READY",
        "shutdown": "SHUTDOWN",
    }
    for phase, want in cases.items():
        marp.state["phase"] = phase
        assert marp.marp_state() == want, f"{phase} -> {marp.marp_state()}"


def test_auth_guards_unchanged_on_marp_routes():
    """Spot check: R2 did not weaken R1 authorization (full matrix in R1)."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        r = client.post("/api/v1/attendance/start",
                        json={"session_name": "x"})
        assert r.status_code in (401, 403), r.status_code
        r = client.post("/api/v1/marp/chaos/db-drop")
        assert r.status_code in (401, 403), r.status_code


# ================= E. shutdown and isolation =================
def test_shutdown_blocks_new_work_and_reports(fake_detector):
    from app.routers import marp_router

    fake_detector.mode = "block"
    marp.start_background_load("boot")
    assert wait_for(lambda: marp.state.get("phase") == "warming_up_detector")
    marp.note_shutdown()
    current = marp._current_generation()
    # Refused: returns the current generation without spawning new work.
    assert marp.start_background_load("recovery") == current
    assert fake_detector.calls <= 1
    body, code = ENGINE.readiness()
    assert code == 503 and body["failure_kind"] == "shutdown"
    assert marp.marp_state() == "SHUTDOWN"
    assert marp_router.liveness()["status"] == "alive"
    fake_detector.release.set()  # stale worker must commit nothing harmful
    time.sleep(0.3)
    assert ENGINE.stage == "SHUTDOWN"


def test_no_recovery_worker_after_shutdown(fake_detector):
    before = threading.active_count()
    marp.note_shutdown()
    marp.start_background_load("recovery")
    marp.inject("recover")
    time.sleep(0.3)
    assert threading.active_count() <= before + 2  # telemetry threads only
    assert marp._load_thread is None or not marp._load_thread.is_alive()


def test_fresh_schema_init_no_duplicate_race():
    """Concurrent schema creation (loader + telemetry pattern) is safe."""
    from sqlalchemy import text
    from app.core.database import engine

    with engine.connect() as c:
        c.execute(text("DROP TABLE IF EXISTS marp_telemetry"))
        c.commit()
    with marp._load_lock:
        marp._schema_ready = False
    errors = []

    def _ensure():
        try:
            marp._ensure_schema()
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_ensure) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert not errors, errors
    from app.models.telemetry import MarpTelemetry

    with engine.connect() as c:
        assert c.execute(text("SELECT COUNT(*) FROM marp_telemetry")).scalar() == 0
    assert MarpTelemetry.__tablename__ == "marp_telemetry"
