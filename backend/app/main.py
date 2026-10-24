"""FACEATTEND — FastAPI lifespan + router mount + legacy compat.

New MARP surface:  /api/v1/marp/*, /api/v1/auth/*, /api/v1/students/*,
                    /api/v1/attendance/*, /api/v1/settings/*
Legacy surface (DevOps contract, tests/fault_injection.py):
                    /healthz/*, /api/status, /api/chaos*, /api/detect*,
                    /ws/detect, /api/logs, /api/auth/login,
                    /api/students/*, /api/attendance/*
"""
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .core.database import SessionLocal, engine
from .models.detection import DetectionEvent  # noqa: F401 (register tables)
from .models.student import Student  # noqa: F401
from .models.attendance import AttendanceSession, AttendanceRecord  # noqa: F401
from .models.user import User  # noqa: F401
from .models.telemetry import MarpTelemetry  # noqa: F401 (research telemetry)
from .routers import (attendance_router, auth_router, marp_router,
                      settings_router, students_router)
from .schemas.attendance import FrameIn, OverrideIn, StartIn
from .schemas.marp import ChaosIn, LoginIn
from .services import attendance_service as svc
from .services import face_detection as fd
from .services import face_recognition as fr
from .services import marp_engine as marp


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Orchestrated boot: UNINITIALIZED -> (background) DB_CONNECTED ->
    # LOADING_WEIGHTS -> READY. DB migration + detector pre-warm both run
    # inside marp.load_heavy_model so docker healthchecks observe 503 until
    # READY; lifespan only seeds the stage and starts the worker.
    marp.ENGINE.set_stage("UNINITIALIZED", "starting")
    marp.start_background_load()
    yield
    marp.ENGINE.set_stage(marp.ENGINE.stage, marp.state.get("phase", ""))


app = FastAPI(title="face-attendance (MARP)", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])

app.include_router(marp_router.router)
app.include_router(auth_router.router)
app.include_router(students_router.router)
app.include_router(attendance_router.router)
app.include_router(settings_router.router)


# ---- legacy compat: health / status / chaos ----
@app.get("/healthz/liveness")
def legacy_liveness():
    return {"status": "alive"}


@app.get("/healthz/readiness")
def legacy_readiness():
    body, code = marp_router._readiness_body()
    return JSONResponse(body, status_code=code)


@app.get("/api/status")
def legacy_status():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return {"phase": marp.state["phase"], "model_ready": marp.state["model_ready"],
            "db_connected": db_ok, "uptime_s": round(time.time() - marp.START_TIME, 1),
            "active_session": dict(marp.active_session),
            "simulated_db_failure": marp.SIMULATED_DB_FAILURE,
            "simulated_model_failure": marp.SIMULATED_MODEL_FAILURE}


@app.post("/api/chaos")
def legacy_chaos(c: ChaosIn):
    return marp.inject(c.failure)


@app.post("/api/chaos/db-drop")
def legacy_db_drop():
    return marp_router.db_drop()


@app.post("/api/chaos/unload-model")
def legacy_unload():
    return marp_router.unload_model()


@app.post("/api/chaos/recover")
def legacy_recover():
    return marp_router.recover()


# ---- legacy compat: domain ----
@app.post("/api/auth/login")
def legacy_login(body: LoginIn):
    return auth_router.login(body)


@app.post("/api/students/enroll")
def legacy_enroll(body: students_router.EnrollIn):
    return students_router.enroll(body)


@app.get("/api/students")
def legacy_list_students():
    return students_router.list_students()


@app.get("/api/students/{student_id}/attendance")
def legacy_student_attendance(student_id: str):
    return students_router.student_attendance(student_id)


@app.post("/api/detect")
def legacy_detect(frame: FrameIn):
    if not marp.state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": marp.state["phase"]},
                            status_code=503)
    raw = fd.decode_frame(frame.image)
    dets = fr.detect_and_identify(raw)
    fr.log_detections(dets)
    return {"detections": dets, "active_session": dict(marp.active_session)}


@app.post("/api/detect/annotated")
def legacy_detect_annotated(frame: FrameIn):
    return attendance_router.detect_annotated(frame)


@app.websocket("/ws/detect")
async def legacy_ws(ws: WebSocket):
    """Legacy WS mirror — same JWT ?token= guard + process_live_frame()."""
    from .core.security import verify_token as _verify

    await ws.accept()
    token = ws.query_params.get("token", "")
    payload = _verify(token) if token else None
    if payload is None or not payload.get("sub"):
        try:
            await ws.close(code=4401)
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
                                        "active_session": dict(marp.active_session)})
                except Exception:
                    break
                continue
            try:
                result = svc.process_live_frame(msg.get("image", ""))
            except Exception as e:
                try:
                    await ws.send_json({"error": f"inference failed: {e}",
                                        "detections": []})
                except Exception:
                    break
                continue
            try:
                await ws.send_json(result)
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/logs")
def legacy_logs(limit: int = 20):
    s = SessionLocal()
    try:
        rows = s.query(DetectionEvent).order_by(
            DetectionEvent.id.desc()).limit(limit).all()
        return [{"id": r.id,
                 "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                 "detection_type": r.detection_type, "confidence": r.confidence}
                for r in rows]
    finally:
        s.close()


@app.post("/api/attendance/start")
def legacy_start(body: StartIn):
    return svc.start_session(body.session_name)


@app.post("/api/attendance/stop")
def legacy_stop():
    return svc.stop_session()


@app.get("/api/attendance/roster")
def legacy_roster(session_id: int | None = None):
    return attendance_router.roster(session_id)


@app.get("/api/attendance/sessions")
def legacy_sessions(limit: int = 20):
    return attendance_router.sessions(limit)


@app.post("/api/attendance/override")
def legacy_override(body: OverrideIn):
    return attendance_router.override(body)
