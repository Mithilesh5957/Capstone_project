"""FACEATTEND R9: matcher correctness + attendance fail-safe tests.

Scope: explicit validation of comparison inputs (None/malformed/NaN/inf/
wrong-length), the documented <= threshold rule (default REID_THRESHOLD=0.85,
UNCALIBRATED against real data — threshold value itself is not under test),
1-NN selection, no-face/no-template paths, enrollment 422 fail-closed paths,
and attendance dedup/rejection paths. No accuracy is measured here; no real
faces are used (synthetic 4096-dim vectors + blank JPEGs only).
"""
import base64
import os
import sys

import cv2
import numpy as np
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

import app.core.config as config  # noqa: E402
import app.services.attendance_service as svc  # noqa: E402
import app.services.face_detection as fd  # noqa: E402
import app.services.face_recognition as fr  # noqa: E402
import app.services.marp_engine as marp  # noqa: E402
from app.core.database import Base, SessionLocal  # noqa: E402
from app.models.attendance import AttendanceRecord  # noqa: E402
from app.models.student import Student  # noqa: E402
from app.schemas.student import EnrollIn  # noqa: E402

DIM = 4096


def _basis(i=0):
    v = [0.0] * DIM
    v[i] = 1.0
    return v


def _opposite(v):
    return [-x for x in v]


class _Row:
    """Minimal stand-in for a Student row (embeddings only)."""

    def __init__(self, emb):
        self.embeddings = emb


# ---------- euclidean validity ----------

def test_euclidean_identical_is_zero():
    assert fr.euclidean(_basis(), _basis()) == 0.0


def test_euclidean_opposite_is_two():
    assert fr.euclidean(_basis(), _opposite(_basis())) == pytest.approx(2.0)


def test_euclidean_invalid_inputs_are_inf():
    bad = [None, [], [1.0, 2.0], "not-a-vector",
           [float("nan")] * DIM, [float("inf")] * DIM]
    for b in bad:
        assert fr.euclidean(_basis(), b) == float("inf")
        assert fr.euclidean(b, _basis()) == float("inf")


# ---------- match_student boundary behavior ----------

def test_match_accepts_below_threshold():
    row = _Row(_basis())
    got, dist = fr.match_student(_basis(), [row])
    assert got is row and dist == 0.0


def test_match_rejects_above_threshold():
    row = _Row(_basis())
    got, dist = fr.match_student(_opposite(_basis()), [row])
    assert (got, dist) == (None, None)


def test_match_at_threshold_follows_le_rule(monkeypatch):
    v0 = _basis()
    w = [0.63875, (1 - 0.63875 ** 2) ** 0.5] + [0.0] * (DIM - 2)
    d = fr.euclidean(v0, w)
    assert d == pytest.approx(0.85)
    row = _Row(_basis())
    monkeypatch.setattr(config, "REID_THRESHOLD", d)
    got, dist = fr.match_student(w, [row])
    assert got is row and dist == pytest.approx(d)


def test_match_picks_minimum_among_candidates():
    near, far = _Row(_basis(1)), _Row(_basis(0))
    probe = _basis(1)
    got, dist = fr.match_student(probe, [far, near])
    assert got is near and dist == 0.0


def test_match_skips_malformed_stored_templates():
    bad_rows = [_Row(None), _Row([]), _Row("junk"),
                _Row([1.0] * 100), _Row([float("nan")] * DIM),
                _Row([float("inf")] * DIM)]
    assert fr.match_student(_basis(), bad_rows) == (None, None)
    good = _Row(_basis())
    got, _ = fr.match_student(_basis(), bad_rows + [good])
    assert got is good


def test_match_invalid_probe_never_matches():
    stored = _Row(_basis())
    for bad in (None, [], [1.0, 2.0], "junk",
                [float("nan")] * DIM, [float("inf")] * DIM):
        assert fr.match_student(bad, [stored]) == (None, None)


def test_match_no_students_no_match():
    assert fr.match_student(_basis(), []) == (None, None)


# ---------- enrollment fail-closed paths (isolated PG) ----------

@pytest.fixture()
def clean_db():
    Base.metadata.create_all(bind=__import__(
        "app.core.database", fromlist=["engine"]).engine)
    s = SessionLocal()
    try:
        for m in (AttendanceRecord, Student):
            s.query(m).delete()
        s.commit()
        yield s
    finally:
        s.close()


@pytest.fixture()
def marp_state():
    snap_session = dict(marp.active_session)
    snap_memory = set(marp.marked_memory)
    snap_ready = marp.state.get("model_ready")
    yield
    marp.active_session.clear()
    marp.active_session.update(snap_session)
    marp.marked_memory.clear()
    marp.marked_memory.update(snap_memory)
    marp.state["model_ready"] = snap_ready


def _b64_jpeg(img):
    ok, buf = cv2.imencode(".jpg", img)
    assert ok
    return base64.b64encode(bytes(buf)).decode()


def test_enroll_rejects_invalid_base64_422(clean_db, marp_state):
    from fastapi import HTTPException

    marp.state["model_ready"] = True
    with pytest.raises(HTTPException) as ei:
        from app.routers.students_router import enroll_impl
        enroll_impl(EnrollIn(student_id="S1", name="N", images=["!!!"]))
    assert ei.value.status_code == 422


def test_enroll_rejects_faceless_image_422(clean_db, marp_state):
    from fastapi import HTTPException

    marp.state["model_ready"] = True
    blank = np.zeros((480, 640, 3), dtype=np.uint8)
    with pytest.raises(HTTPException) as ei:
        from app.routers.students_router import enroll_impl
        enroll_impl(EnrollIn(student_id="S1", name="N",
                             images=[_b64_jpeg(blank)]))
    assert ei.value.status_code == 422
    assert "no usable face" in ei.value.detail


# ---------- attendance safety (isolated PG) ----------

def _seed_student(s, sid="S1", emb=None):
    if emb is None:
        emb = _basis()
    s.add(Student(student_id=sid, name="Stu", branch="CSE", embeddings=emb))
    s.commit()


def _present_rows(s, sid="S1"):
    return s.query(AttendanceRecord).filter(
        AttendanceRecord.student_id == sid).all()


def test_mark_present_no_session_records_nothing(clean_db, marp_state):
    _seed_student(clean_db)
    assert svc.maybe_mark_present("S1") is False
    assert _present_rows(clean_db) == []


def test_mark_present_once_then_dedup(clean_db, marp_state):
    _seed_student(clean_db)
    svc.start_session("R9")
    assert svc.maybe_mark_present("S1") is True
    assert svc.maybe_mark_present("S1") is False
    rows = _present_rows(clean_db)
    assert len(rows) == 1 and rows[0].status == "Present"


def test_mark_present_invalid_student_records_nothing(clean_db, marp_state):
    _seed_student(clean_db)
    svc.start_session("R9")
    assert svc.maybe_mark_present("GHOST") is False
    assert _present_rows(clean_db, "GHOST") == []


def test_detect_wiring_marks_only_on_match(clean_db, marp_state, monkeypatch):
    _seed_student(clean_db)
    svc.start_session("R9")
    monkeypatch.setattr(
        fd, "detect_faces_jpeg",
        lambda jpeg: [{"type": "face", "confidence": 0.9, "bbox": [0, 0, 9, 9]}])
    monkeypatch.setattr(fr, "embedding_for_bbox", lambda jpeg, bbox: _basis())
    out = fr.detect_and_identify(b"fake-jpeg-bytes")
    assert len(out) == 1 and out[0]["student_id"] == "S1"
    assert len(_present_rows(clean_db)) == 1


def test_detect_wiring_unknown_face_marks_nothing(
        clean_db, marp_state, monkeypatch):
    svc.start_session("R9")
    monkeypatch.setattr(
        fd, "detect_faces_jpeg",
        lambda jpeg: [{"type": "face", "confidence": 0.9, "bbox": [0, 0, 9, 9]}])
    monkeypatch.setattr(fr, "embedding_for_bbox", lambda jpeg, bbox: _basis())
    out = fr.detect_and_identify(b"fake-jpeg-bytes")
    assert len(out) == 1 and out[0]["student_id"] is None
    assert "Unknown Face" in out[0]["name"]
    clean_db.expire_all()
    assert clean_db.query(AttendanceRecord).all() == [] or all(
        r.status == "Absent" for r in clean_db.query(AttendanceRecord).all())
