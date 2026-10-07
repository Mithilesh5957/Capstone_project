import base64
from datetime import datetime
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from ..core import config
from ..core.database import SessionLocal
from ..models.attendance import AttendanceRecord
from ..schemas.attendance import FrameIn, OverrideIn, StartIn
from ..services import attendance_service as svc
from ..services import face_detection as fd
from ..services import face_recognition as fr
from ..services import marp_engine as marp

router = APIRouter(prefix="/api/v1/attendance", tags=["attendance"])


def _guard_ready():
    if not marp.state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": marp.state["phase"]},
                            status_code=503)
    return None


@router.post("/start")
def start(body: StartIn):
    return svc.start_session(body.session_name)


@router.post("/stop")
def stop():
    return svc.stop_session()


@router.get("/roster")
def roster(session_id: int | None = None):
    sid = session_id if session_id is not None else marp.active_session["id"]
    if sid is None:
        return {"session_id": None, "records": []}
    return svc.session_summary(sid)


@router.get("/sessions")
def sessions(limit: int = 20):
    from ..models.attendance import AttendanceSession
    s = SessionLocal()
    try:
        rows = s.query(AttendanceSession).order_by(
            AttendanceSession.id.desc()).limit(limit).all()
        out = []
        for sess in rows:
            summ = svc.session_summary(sess.id)
            out.append({"session_id": sess.id, "session_name": sess.session_name,
                        "date": sess.date.isoformat() if sess.date else None,
                        "total": summ["total"], "present": summ["present"],
                        "absent": summ["absent"]})
        return out
    finally:
        s.close()


@router.get("/export.csv")
def export_csv(session_id: int):
    return PlainTextResponse(svc.export_csv(session_id), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f"attachment; filename=session_{session_id}.csv"})


@router.post("/override")
def override(body: OverrideIn):
    if body.status not in ("Present", "Absent"):
        raise HTTPException(status_code=422, detail="status must be Present|Absent")
    s = SessionLocal()
    try:
        rec = s.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == body.session_id,
            AttendanceRecord.student_id == body.student_id).first()
        now = datetime.now() if body.status == "Present" else None
        if rec is None:
            s.add(AttendanceRecord(session_id=body.session_id,
                                   student_id=body.student_id,
                                   status=body.status, marked_at=now))
        else:
            rec.status, rec.marked_at = body.status, now
        s.commit()
        with marp.session_lock():
            key = (body.session_id, body.student_id)
            if body.status == "Present":
                marp.marked_memory.add(key)
            else:
                marp.marked_memory.discard(key)
        return {"ok": True, "session_id": body.session_id,
                "student_id": body.student_id, "status": body.status}
    except HTTPException:
        raise
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"override failed: {e}")
    finally:
        s.close()


@router.post("/detect")
def detect(frame: FrameIn):
    g = _guard_ready()
    if g:
        return g
    raw = fd.decode_frame(frame.image)
    dets = fr.detect_and_identify(raw)
    fr.log_detections(dets)
    return {"detections": dets, "active_session": dict(marp.active_session)}


@router.post("/detect/annotated")
def detect_annotated(frame: FrameIn):
    g = _guard_ready()
    if g:
        return g
    raw = fd.decode_frame(frame.image)
    dets = fr.detect_and_identify(raw)
    fr.log_detections(dets)
    annotated = fd.annotate_frame(raw, dets)
    data_url = ("data:image/jpeg;base64," + base64.b64encode(annotated).decode()
                if annotated else None)
    return {"detections": dets, "image": data_url,
            "size": {"w": config.FRAME_W, "h": config.FRAME_H},
            "active_session": dict(marp.active_session)}


@router.websocket("/ws/detect")
async def detect_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if not marp.state["model_ready"]:
                await ws.send_json({"error": "model loading",
                                    "phase": marp.state["phase"]})
                continue
            raw = fd.decode_frame(msg.get("image", ""))
            dets = fr.detect_and_identify(raw)
            fr.log_detections(dets)
            await ws.send_json({"detections": dets,
                                "active_session": dict(marp.active_session)})
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
