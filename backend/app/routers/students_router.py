import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from ..core.database import SessionLocal
from ..core.security import require_admin
from ..models.student import Student
from ..schemas.student import EnrollIn
from ..services import face_detection as fd
from ..services import face_recognition as fr
from ..services import marp_engine as marp

router = APIRouter(prefix="/api/v1/students", tags=["students"])


@router.post("/enroll")
def enroll(body: EnrollIn, _admin: dict = Depends(require_admin)):
    if not marp.state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": marp.state["phase"]},
                            status_code=503)
    sid, name = (body.student_id or "").strip(), (body.name or "").strip()
    if not sid or not name or not body.images:
        raise HTTPException(status_code=422,
                            detail="student_id, name and images[] required")
    vecs = []
    for i, b64 in enumerate(body.images[:8]):
        try:
            raw = fd.decode_frame(b64)
        except HTTPException:
            raise HTTPException(status_code=422, detail=f"image[{i}] invalid base64")
        v = fr.embedding_from_bytes(raw)
        if v is None:
            raise HTTPException(status_code=422, detail=f"image[{i}] has no usable face")
        vecs.append(np.array(v, dtype=np.float32))
    mean_vec = sum(vecs) / len(vecs)
    n = float(np.linalg.norm(mean_vec))
    if n > 1e-6:
        mean_vec = mean_vec / n
    s = SessionLocal()
    try:
        row = s.query(Student).filter(Student.student_id == sid).first()
        if row:
            row.name, row.branch, row.embeddings = name, body.branch, mean_vec.tolist()
        else:
            s.add(Student(student_id=sid, name=name, branch=body.branch,
                          embeddings=mean_vec.tolist()))
        s.commit()
        return {"ok": True, "student_id": sid, "name": name,
                "angles_used": len(vecs), "embedding_dim": len(mean_vec)}
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"enroll failed: {e}")
    finally:
        s.close()


@router.get("")
def list_students():
    s = SessionLocal()
    try:
        rows = s.query(Student).order_by(Student.student_id).all()
        return [{"student_id": r.student_id, "name": r.name, "branch": r.branch,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        s.close()


@router.get("/{student_id}/attendance")
def student_attendance(student_id: str):
    from ..models.attendance import AttendanceRecord, AttendanceSession
    s = SessionLocal()
    try:
        row = s.query(Student).filter(Student.student_id == student_id).first()
        recs = (s.query(AttendanceRecord, AttendanceSession)
                .join(AttendanceSession,
                      AttendanceRecord.session_id == AttendanceSession.id)
                .filter(AttendanceRecord.student_id == student_id)
                .order_by(AttendanceSession.id.desc()).all())
        total, present = len(recs), sum(1 for r, _ in recs if r.status == "Present")
        return {"student_id": student_id, "name": row.name if row else student_id,
                "branch": row.branch if row else "", "total_sessions": total,
                "present": present,
                "percentage": round(present / total * 100, 1) if total else 0.0,
                "history": [{"session_id": sess.id, "session_name": sess.session_name,
                             "date": sess.date.isoformat() if sess.date else None,
                             "status": r.status,
                             "marked_at": r.marked_at.isoformat() if r.marked_at else None}
                            for r, sess in recs]}
    finally:
        s.close()
