"""Session lifecycle + roster + CSV export + live-frame pipeline."""
import csv
import io
from datetime import datetime
from ..core.database import SessionLocal
from ..models.attendance import AttendanceRecord, AttendanceSession
from ..models.student import Student
from . import marp_engine as marp


def maybe_mark_present(student_row_id: str) -> bool:
    if marp.active_session["id"] is None:
        return False
    key = (marp.active_session["id"], student_row_id)
    with marp.session_lock():
        if key in marp.marked_memory:
            return False
        marp.marked_memory.add(key)
    s = SessionLocal()
    try:
        rec = s.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == marp.active_session["id"],
            AttendanceRecord.student_id == student_row_id).first()
        if rec is None:
            rec = AttendanceRecord(session_id=marp.active_session["id"],
                                   student_id=student_row_id, status="Present",
                                   marked_at=datetime.now())
            s.add(rec)
        elif rec.status != "Present":
            rec.status = "Present"
            rec.marked_at = datetime.now()
        else:
            return False
        s.commit()
        return True
    except Exception:
        s.rollback()
        with marp.session_lock():
            marp.marked_memory.discard(key)
        return False
    finally:
        s.close()


def session_summary(sid: int):
    s = SessionLocal()
    try:
        recs = s.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == sid).all()
        sess = s.query(AttendanceSession).filter(
            AttendanceSession.id == sid).first()
        present = [r for r in recs if r.status == "Present"]
        names = {r.student_id: "" for r in recs}
        for st in s.query(Student).all():
            if st.student_id in names:
                names[st.student_id] = st.name
        return {"session_id": sid,
                "session_name": sess.session_name if sess else "",
                "total": len(recs), "present": len(present),
                "absent": len(recs) - len(present),
                "records": [{"student_id": r.student_id,
                             "name": names.get(r.student_id, ""),
                             "status": r.status,
                             "marked_at": r.marked_at.isoformat() if r.marked_at else None}
                            for r in sorted(recs, key=lambda r: r.student_id)]}
    finally:
        s.close()


def start_session(session_name: str):
    from fastapi import HTTPException
    with marp.session_lock():
        if marp.active_session["id"] is not None:
            raise HTTPException(
                status_code=409,
                detail=f"session {marp.active_session['id']} already active")
    s = SessionLocal()
    try:
        sess = AttendanceSession(session_name=session_name or "Session")
        s.add(sess)
        s.flush()
        students = s.query(Student).all()
        for st in students:
            s.add(AttendanceRecord(session_id=sess.id, student_id=st.student_id,
                                   status="Absent", marked_at=None))
        s.commit()
        sid = sess.id
        n = len(students)
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"start failed: {e}")
    finally:
        s.close()
    with marp.session_lock():
        marp.active_session.update({"id": sid, "name": session_name})
        marp.marked_memory.clear()
    return {"ok": True, "session_id": sid, "session_name": session_name,
            "total_students": n}


def stop_session():
    from fastapi import HTTPException
    with marp.session_lock():
        sid = marp.active_session["id"]
        if sid is None:
            raise HTTPException(status_code=409, detail="no active session")
        marp.active_session.update({"id": None, "name": None})
        marp.marked_memory.clear()
    return {"ok": True, "summary": session_summary(sid)}


def export_csv(sid: int) -> str:
    summary = session_summary(sid)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["student_id", "name", "status", "marked_at"])
    w.writeheader()
    for r in summary["records"]:
        w.writerow(r)
    return buf.getvalue()


def process_live_frame(image_b64: str) -> dict:
    """Secure live-frame pipeline for `/ws/detect`.

    Accepts a base64 JPEG (data-URL or raw), runs
    `face_recognition.detect_and_identify()` — which internally calls
    `maybe_mark_present()` with `marked_memory` deduplication — then logs
    detections. Returns dets + newly-marked ids + active session so the
    frontend can update roll call without an extra roster round-trip.

    `marked_memory` guarantees idempotency: a student already present in
    the active session is NOT re-written (DB UPDATE skipped, returns False).
    """
    from fastapi import HTTPException

    from . import face_detection as fd
    from . import face_recognition as fr

    if not image_b64:
        raise HTTPException(status_code=422, detail="empty frame")
    try:
        raw = fd.decode_frame(image_b64)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid frame: {e}")

    # Snapshot dedup set so we can report who was *newly* marked by this frame.
    try:
        before = set(marp.marked_memory)
        active_id = marp.active_session.get("id")
    except Exception:
        before, active_id = set(), None

    dets = fr.detect_and_identify(raw)
    try:
        fr.log_detections(dets)
    except Exception:
        pass

    newly_marked: list[str] = []
    try:
        after = set(marp.marked_memory)
        for sid in {
            str(d.get("student_id") or "")
            for d in dets
            if d.get("student_id")
        }:
            if active_id is not None and (active_id, sid) in after and (active_id, sid) not in before:
                newly_marked.append(sid)
    except Exception:
        newly_marked = []

    return {
        "detections": dets,
        "newly_marked": newly_marked,
        "active_session": marp.session_snapshot(),
    }
