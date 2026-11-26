"""FACEATTEND R5: roster <-> CSV export correctness (FR-07).

Verifies the exported CSV contains exactly the authoritative roster data
(same session_summary source as the roster endpoint), including header,
row order, status values after override, and the empty-session case.
No backend API changes; auth is covered by the R1 suite.
"""
import csv
import io
import os
import sys

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
if "R1_TEST_DATABASE_URL" in os.environ:
    os.environ["DATABASE_URL"] = os.environ["R1_TEST_DATABASE_URL"]
else:
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg://postgres@localhost/faceattend_r1_test",
    )

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app.routers.attendance_router as attendance_router  # noqa: E402
import app.services.attendance_service as svc  # noqa: E402
import app.services.marp_engine as marp  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.student import Student  # noqa: E402

ADMIN = {"sub": "admin", "role": "admin"}


@pytest.fixture()
def isolated_db():
    Base.metadata.create_all(bind=engine)
    s = SessionLocal()
    try:
        from app.models.attendance import AttendanceRecord, AttendanceSession

        for m in (AttendanceRecord, AttendanceSession, Student):
            s.query(m).delete()
        s.commit()
        yield s
    finally:
        s.close()


@pytest.fixture()
def clean_marp():
    snap_session = dict(marp.active_session)
    snap_memory = set(marp.marked_memory)
    marp.active_session.update({"id": None, "name": None})
    marp.marked_memory.clear()
    yield
    marp.active_session.clear()
    marp.active_session.update(snap_session)
    marp.marked_memory.clear()
    marp.marked_memory.update(snap_memory)


def _seed_students():
    s = SessionLocal()
    try:
        for sid, name in (("2100030001", "Asha Rao"), ("2100030002", "Ben Cole")):
            if s.query(Student).filter(Student.student_id == sid).first() is None:
                s.add(Student(student_id=sid, name=name, branch="CSE",
                              embeddings=[]))
        s.commit()
    finally:
        s.close()


def test_export_matches_roster_records(isolated_db, clean_marp):
    _seed_students()
    started = svc.start_session("R5 Export Check")
    sid = started["session_id"]
    try:
        # Flip one record to Present via the same override path the UI uses.
        from app.schemas.attendance import OverrideIn

        attendance_router.override(
            OverrideIn(session_id=sid, student_id="2100030001",
                       status="Present"),
            ADMIN,
        )
        roster = attendance_router.roster_impl(sid)
        assert roster["session_id"] == sid
        assert roster["total"] == 2
        assert {r["status"] for r in roster["records"]} == {"Present", "Absent"}

        text = svc.export_csv(sid)
        rows = list(csv.DictReader(io.StringIO(text)))
        assert [r["student_id"] for r in rows] == [
            r["student_id"] for r in roster["records"]]
        for csv_row, rec in zip(rows, roster["records"]):
            assert csv_row["student_id"] == rec["student_id"]
            assert csv_row["name"] == rec["name"]
            assert csv_row["status"] == rec["status"]
            assert (csv_row["marked_at"] or "") == (rec["marked_at"] or "")
    finally:
        try:
            svc.stop_session()
        except Exception:
            pass


def test_export_empty_session_has_header_only(isolated_db, clean_marp):
    started = svc.start_session("R5 Empty Export")
    sid = started["session_id"]
    try:
        text = svc.export_csv(sid)
        lines = text.splitlines()
        assert lines[0] == "student_id,name,status,marked_at"
        # No students enrolled: header only, no data rows.
        assert list(csv.DictReader(io.StringIO(text))) == []
    finally:
        try:
            svc.stop_session()
        except Exception:
            pass
