"""Real-time video analytics backend: FastAPI + OpenCV + PostgreSQL."""
import base64
import os
import threading
import time

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Float, Integer, String, create_engine, func, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analytics:analytics@db:5432/analytics")
MODEL_LOAD_SECONDS = int(os.getenv("MODEL_LOAD_SECONDS", "15"))  # 10-20s synthetic delay

START_TIME = time.time()
state = {"phase": "starting", "model_ready": False, "db_ready": False}
face_cascade = None

Base = declarative_base()

class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    detection_type = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)

engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                         connect_args={"connect_timeout": 3})  # bounded probe for readiness live-check
Session = sessionmaker(bind=engine)

app = FastAPI(title="video-analytics")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def load_heavy_model():
    """Simulate loading ML weights, then verify DB. Runs in background thread."""
    global face_cascade
    state["phase"] = "loading_model_weights"
    time.sleep(MODEL_LOAD_SECONDS)  # synthetic 10-20s delay

    state["phase"] = "warming_up_detector"
    try:
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if face_cascade.empty():
            raise RuntimeError("Haar cascade failed to load (empty classifier)")
    except Exception as e:
        state["phase"] = f"detector_failed: {e}"
        return
    time.sleep(1)

    state["phase"] = "connecting_postgres"
    try:
        Base.metadata.create_all(engine)
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        state["db_ready"] = True
    except Exception as e:
        state["phase"] = f"db_failed: {e}"
        return

    state["model_ready"] = True
    state["phase"] = "ready"


@app.on_event("startup")
def on_startup():
    threading.Thread(target=load_heavy_model, daemon=True).start()


@app.get("/healthz/liveness")
def liveness():
    return {"status": "alive"}


@app.get("/healthz/readiness")
def readiness():
    # Live-check Postgres so a DB failure flips readiness back to 503 (AC-2);
    # cached flags alone would stay stale at 200 after a mid-run DB kill.
    if state["model_ready"]:
        try:
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            state["db_ready"] = True
        except Exception:
            state["db_ready"] = False
    ready = state["model_ready"] and state["db_ready"]
    body = {"phase": state["phase"], "model_ready": state["model_ready"],
            "db_ready": state["db_ready"], "uptime_s": round(time.time() - START_TIME, 1)}
    return JSONResponse(body, status_code=200 if ready else 503)


@app.get("/api/status")  # polled by DevOps Telemetry Monitor
def status():
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    state["db_ready"] = db_ok and state["phase"] == "ready"
    return {"phase": state["phase"], "model_ready": state["model_ready"],
            "db_connected": db_ok, "uptime_s": round(time.time() - START_TIME, 1)}


def detect_faces_jpeg(jpeg_bytes: bytes):
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4) if face_cascade else []
    h, w = gray.shape
    out = []
    for (x, y, fw, fh) in faces:  # Haar has no score -> synthesize from relative size
        conf = round(min(0.99, 0.80 + (fw * fh) / (w * h) * 2), 2)
        out.append({"type": "face", "confidence": conf,
                    "bbox": [int(x), int(y), int(fw), int(fh)]})
    return out


def log_detections(dets: list):
    if not dets:
        return
    s = Session()
    try:
        s.add_all([DetectionEvent(detection_type=d["type"], confidence=d["confidence"]) for d in dets])
        s.commit()
    finally:
        s.close()


class FrameIn(BaseModel):
    image: str  # "data:image/jpeg;base64,..." or raw base64


def decode_frame(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data, validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid base64 image")


@app.post("/api/detect")
def detect_rest(frame: FrameIn):
    if not state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": state["phase"]}, status_code=503)
    dets = detect_faces_jpeg(decode_frame(frame.image))
    log_detections(dets)
    return {"detections": dets}


@app.websocket("/ws/detect")
async def detect_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if not state["model_ready"]:
                await ws.send_json({"error": "model loading", "phase": state["phase"]})
                continue
            dets = detect_faces_jpeg(decode_frame(msg.get("image", "")))
            log_detections(dets)
            await ws.send_json({"detections": dets})
    except WebSocketDisconnect:
        pass


@app.get("/api/logs")
def recent_logs(limit: int = 20):
    s = Session()
    try:
        rows = s.query(DetectionEvent).order_by(DetectionEvent.id.desc()).limit(limit).all()
        return [{"id": r.id, "timestamp": r.timestamp.isoformat() if r.timestamp else None,
                 "detection_type": r.detection_type, "confidence": r.confidence} for r in rows]
    finally:
        s.close()


class ChaosIn(BaseModel):
    failure: str = "db_drop"  # db_drop | model_unload | recover


@app.post("/api/chaos")
def chaos(c: ChaosIn):
    """Simulate service disconnects for the frontend chaos button."""
    if c.failure == "db_drop":
        engine.dispose()
        state["db_ready"] = False
        state["phase"] = "chaos: postgres unreachable"
    elif c.failure == "model_unload":
        state["model_ready"] = False
        state["phase"] = "chaos: model unloaded"
    elif c.failure == "recover":
        state["phase"] = "reloading"
        threading.Thread(target=load_heavy_model, daemon=True).start()
    return {"phase": state["phase"]}
