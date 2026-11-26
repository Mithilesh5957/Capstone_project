"""R10 schema-startup concurrency tests (fresh disposable PostgreSQL only).

Exercises the REAL production initializer (marp_engine._ensure_schema) from
genuinely independent OS processes. Threads are used only to launch and wait
for subprocesses; all DDL coordination happens cross-process inside the
database. No real data, no shared project databases.
"""
import concurrent.futures as cf
import os
import subprocess
import sys
import uuid

import pytest
import sqlalchemy as sa

os.environ.setdefault("ENVIRONMENT", "test")
if "R1_TEST_DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["R1_TEST_DATABASE_URL"]
else:
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://postgres@localhost/faceattend_r1_test",
    )

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.services.marp_engine as marp  # noqa: E402
from app.core.database import Base, engine  # noqa: E402
from app.models.student import Student  # noqa: E402

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..")
EXPECTED_TABLES = {"students", "users", "attendance_sessions",
                   "attendance_records", "detection_events", "marp_telemetry"}

INIT_SCRIPT = (
    "import os, sys; sys.path.insert(0, os.getcwd()); "
    # Import app.main first: registers every model (mirrors production
    # startup imports) so _ensure_schema covers the full schema, not just
    # the telemetry table it imports itself.
    "from app import main as _app_main; "
    "from app.services import marp_engine as m; m._ensure_schema(); "
    "print('INIT_OK', flush=True)"
)


def _server_engine():
    url = sa.engine.make_url(os.environ["DATABASE_URL"])
    maint = url.set(database="postgres")
    return sa.create_engine(maint, isolation_level="AUTOCOMMIT")


def _fresh_db_name():
    return "r10_" + uuid.uuid4().hex[:10]


def _db_url_for(name):
    # NOTE: str(URL) redacts the password as "***" — always render with
    # hide_password=False, otherwise every derived URL authenticates as the
    # literal user "***" and fails. (Diagnosed 2026-10-29.)
    return sa.engine.make_url(os.environ["DATABASE_URL"]).set(
        database=name).render_as_string(hide_password=False)


def _create_db(name):
    assert name.replace("_", "").isalnum(), name
    eng = _server_engine()
    try:
        with eng.connect() as c:
            c.execute(sa.text(f'CREATE DATABASE "{name}"'))
    finally:
        eng.dispose()


def _drop_db(name):
    eng = _server_engine()
    try:
        with eng.connect() as c:
            c.execute(sa.text(
                f'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                f"WHERE datname = '{name}' AND pid <> pg_backend_pid()"))
            c.execute(sa.text(f'DROP DATABASE "{name}" WITH (FORCE)'))
    finally:
        eng.dispose()


@pytest.fixture()
def fresh_db():
    name = _fresh_db_name()
    _create_db(name)
    try:
        yield _db_url_for(name)
    finally:
        _drop_db(name)


def _run_init(db_url, timeout=120):
    env = dict(os.environ, DATABASE_URL=db_url, ENVIRONMENT="test")
    return subprocess.run(
        [sys.executable, "-c", INIT_SCRIPT],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True,
        timeout=timeout)


def test_concurrent_first_time_init_from_separate_processes(fresh_db):
    """Four independent processes initialize the same empty database."""
    with cf.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(_run_init, [fresh_db] * 4))
    for i, r in enumerate(results):
        assert r.returncode == 0, f"proc {i} rc={r.returncode}: {r.stderr[-2000:]}"
        assert "INIT_OK" in r.stdout, f"proc {i} stdout: {r.stdout[-500:]}"
        assert "Traceback" not in r.stderr, f"proc {i} stderr: {r.stderr[-2000:]}"


def test_schema_integrity_after_concurrent_init(fresh_db):
    _run_init(fresh_db)
    eng = sa.create_engine(fresh_db)
    try:
        tables = set(sa.inspect(eng).get_table_names())
        assert EXPECTED_TABLES <= tables, tables
        with eng.begin() as c:
            c.execute(Student.__table__.insert().values(
                student_id="R10T", name="T", branch="CSE", embeddings=[]))
            n = c.execute(sa.text(
                "SELECT count(*) FROM students")).scalar()
            assert n == 1
    finally:
        eng.dispose()


def test_repeat_init_is_idempotent(fresh_db):
    r1 = _run_init(fresh_db)
    r2 = _run_init(fresh_db)
    assert (r1.returncode, r2.returncode) == (0, 0)
    assert "INIT_OK" in r1.stdout and "INIT_OK" in r2.stdout
    marp._ensure_schema()  # in-process repeat on the suite DB: must not raise
    marp._ensure_schema()


def test_init_failure_stays_observable_and_data_untouched(fresh_db):
    r0 = _run_init(fresh_db)
    assert r0.returncode == 0, r0.stderr[-2000:]
    eng = sa.create_engine(fresh_db)
    try:
        with eng.begin() as c:
            c.execute(Student.__table__.insert().values(
                student_id="KEEP", name="K", branch="CSE", embeddings=[]))
        before = eng.connect().execute(
            sa.text("SELECT count(*) FROM students")).scalar()
    finally:
        eng.dispose()
    bad = _db_url_for("r10_nonexistent_db_zzz")
    env = dict(os.environ, DATABASE_URL=bad, ENVIRONMENT="test")
    r = subprocess.run(
        [sys.executable, "-c", INIT_SCRIPT],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode != 0, "unreachable DB must fail, not report success"
    assert "INIT_OK" not in r.stdout
    eng = sa.create_engine(fresh_db)
    try:
        after = eng.connect().execute(
            sa.text("SELECT count(*) FROM students")).scalar()
    finally:
        eng.dispose()
    assert after == before == 1


def test_advisory_lock_only_on_postgresql():
    assert marp._uses_advisory_lock(engine) is True
    lite = sa.create_engine("sqlite://")
    try:
        assert marp._uses_advisory_lock(lite) is False
    finally:
        lite.dispose()
