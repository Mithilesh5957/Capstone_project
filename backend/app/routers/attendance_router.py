import base64
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from ..core import config
from ..core.database import SessionLocal
from ..core.security import require_admin, verify_token
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
def start(body: StartIn, _admin: dict = Depends(require_admin)):
    return svc.start_session(body.session_name)


@router.post("/stop")
def stop(_admin: dict = Depends(require_admin)):
    return svc.stop_session()


def roster_impl(session_id: int | None = None):
    """Shared roster logic. Callers must enforce auth at their boundary
    (direct calls to the route handler would bypass its Depends)."""
    sid = session_id if session_id is not None else marp.active_session["id"]
    if sid is None:
        return {"session_id": None, "records": []}
    return svc.session_summary(sid)


def sessions_impl(limit: int = 20):
    """Shared sessions logic. Callers must enforce auth at their boundary."""
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


@router.get("/roster")
def roster(session_id: int | None = None, _admin: dict = Depends(require_admin)):
    return roster_impl(session_id)


@router.get("/sessions")
def sessions(limit: int = 20, _admin: dict = Depends(require_admin)):
    return sessions_impl(limit)


@router.get("/export.csv")
def export_csv(session_id: int, _admin: dict = Depends(require_admin)):
    return PlainTextResponse(svc.export_csv(session_id), media_type="text/csv",
                             headers={"Content-Disposition":
                                      f"attachment; filename=session_{session_id}.csv"})


@router.post("/override")
def override(body: OverrideIn, _admin: dict = Depends(require_admin)):
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
def detect(frame: FrameIn, _admin: dict = Depends(require_admin)):
    g = _guard_ready()
    if g:
        return g
    raw = fd.decode_frame(frame.image)
    dets = fr.detect_and_identify(raw)
    fr.log_detections(dets)
    return {"detections": dets, "active_session": marp.session_snapshot()}


def detect_annotated_impl(frame: FrameIn):
    """Shared annotated-detect logic. Callers must enforce auth at their own
    route boundary."""
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
            "active_session": marp.session_snapshot()}


@router.post("/detect/annotated")
def detect_annotated(frame: FrameIn, _admin: dict = Depends(require_admin)):
    return detect_annotated_impl(frame)


@router.websocket("/ws/detect")
async def detect_ws(ws: WebSocket):
    """Secure live inference socket.

    Auth: `?token=<JWT>` query param (browsers cannot set WS headers).
    Flow: accept -> verify JWT -> loop { recv JSON {image} -> MARP-ready
    guard -> svc.process_live_frame() (detect + dedup-mark + log) -> send
    {detections, newly_marked, active_session} }.
    Backpressure is cooperative: client MUST wait for this ack (or 1s
    timeout) before sending the next frame, keeping Edge CPU bounded.
    """
    # Accept first so we can close with a policy code on auth failure.
    # R1: live inference also marks attendance, so operator role is required
    # (a student JWT alone must not drive the marking pipeline).
    await ws.accept()
    token = ws.query_params.get("token", "")
    payload = verify_token(token) if token else None
    if payload is None or not payload.get("sub"):
        try:
            await ws.close(code=4401)
        except Exception:
            pass
        return
    if payload.get("role") != "admin":
        try:
            await ws.close(code=4403)
        except Exception:
            pass
        return
    try:
        while True:
            try:
                msg = await ws.receive_json()
            except WebSocketDisconnect:
                break
            except Exception:
                # Malformed frame envelope — nack and keep socket alive.
                try:
                    await ws.send_json({"error": "invalid json envelope"})
                except Exception:
                    break
                continue
            if not marp.state["model_ready"]:
                try:
                    await ws.send_json({"error": "model loading",
                                        "phase": marp.state["phase"],
                                        "detections": [],
                                        "active_session": marp.session_snapshot()})
                except Exception:
                    break
                continue
            try:
                result = svc.process_live_frame(msg.get("image", ""))
            except HTTPException as e:
                try:
                    await ws.send_json({"error": e.detail, "detections": []})
                except Exception:
                    break
                continue
            except Exception as e:
                try:
                    await ws.send_json({"error": f"inference failed: {e}",
                                        "detections": []})
                except Exception:
                    break
                continue
            try:
                await ws.send_json(result)
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
