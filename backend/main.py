"""AI Face Detection Attendance System — FastAPI + OpenCV + PostgreSQL.

Modules in this file:
  1. DevOps contract (DO NOT BREAK): /healthz/liveness, /healthz/readiness,
     /api/status, /api/chaos, /api/detect, /ws/detect, /api/logs
  2. Attendance domain: mock auth, 4-angle enrollment, high-precision Haar
     face detection + embedding ReID, session start/stop, roster, override,
     student stats, server-side annotated frames.

Vision pipeline (foreground faces, not room backgrounds):
  frames are normalised to 640x480, then filtered with strict Haar criteria
  (scaleFactor=1.1, minNeighbors=6, minSize=80x80, aspect ratio 0.7-1.3) so
  door frames/arches and wall noise are rejected while real faces pass.
  Annotated output uses neon-green (#00FF00) 2px boxes + name/conf badges.
"""
import base64
import os
import threading
import time
from datetime import date, datetime

import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import (Column, Date, DateTime, Float, ForeignKey, Integer,
                        String, create_engine, func, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker

# ----------------------------------------------------------------------------
# Config / global state
# ----------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analytics:analytics@db:5432/analytics")
MODEL_LOAD_SECONDS = int(os.getenv("MODEL_LOAD_SECONDS", "15"))  # synthetic 10-20s delay
REID_THRESHOLD = float(os.getenv("REID_THRESHOLD", "0.85"))  # Euclidean match gate
EMBED_SIZE = 64  # face chip resized to 64x64 gray -> 4096-dim embedding

# --- High-precision detection tuning (rejects backgrounds, keeps faces) ---
FRAME_W, FRAME_H = 640, 480  # canonical processing resolution (= frontend canvas)
DET_SCALE_FACTOR = 1.1
DET_MIN_NEIGHBORS = 6       # strict: kills weak wall/door-frame positives
DET_MIN_SIZE = (80, 80)     # discards small background artifacts/arches
DET_ASPECT_LO, DET_ASPECT_HI = 0.7, 1.3  # real faces are ~square; arches are not
NEON_GREEN_BGR = (0, 255, 0)  # #00FF00, 2px boxes + filled label badge

START_TIME = time.time()
state = {"phase": "starting", "model_ready": False, "db_ready": False}
face_cascade = None

# Active attendance session + ReID safeguard memory.
# marked_memory mirrors DB so repeats in the same session are instant no-ops
# and never create duplicate rows (UNIQUE(session_id, student_id) backs it).
_session_lock = threading.Lock()
active_session = {"id": None, "name": None}
marked_memory: set = set()

Base = declarative_base()


# ----------------------------------------------------------------------------
# SQLAlchemy models (mirrors database/schema.sql)
# ----------------------------------------------------------------------------
class DetectionEvent(Base):
    __tablename__ = "detection_events"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    detection_type = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)


class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    student_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    branch = Column(String(100), nullable=False, default="CSE")
    # JSONB on postgres; generic JSON fallback keeps local/sqlite imports working
    try:
        embeddings = Column(JSONB, nullable=False, default=list)
    except Exception:  # pragma: no cover - import-time safety
        from sqlalchemy import JSON as _JSON
        embeddings = Column(_JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    id = Column(Integer, primary_key=True)
    session_name = Column(String(200), nullable=False)
    date = Column(Date, nullable=False, default=date.today)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(String(50), ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False)
    status = Column(String(20), nullable=False, default="Absent")
    marked_at = Column(DateTime(timezone=True), nullable=True)


engine = create_engine(DATABASE_URL, pool_pre_ping=True,
                       connect_args={"connect_timeout": 3})  # bounded probe for readiness live-check
Session = sessionmaker(bind=engine)

app = FastAPI(title="face-attendance")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ============================================================================
# DEVOPS CONTRACT — startup, liveness, readiness, status, chaos (UNCHANGED)
# tests/fault_injection.py depends on this exact behaviour.
# ============================================================================
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
        Base.metadata.create_all(engine)  # creates students/sessions/records too
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
            "db_connected": db_ok, "uptime_s": round(time.time() - START_TIME, 1),
            "active_session": dict(active_session)}


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


# ============================================================================
# Face pipeline: detect -> embed -> ReID match
# ============================================================================
def decode_frame(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data, validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid base64 image")


def _decode_bgr(jpeg_bytes: bytes):
    img = cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)
    return img  # None if corrupt


def _to_canonical(img: np.ndarray) -> np.ndarray:
    """Normalise every frame to 640x480 so bboxes align 1:1 with the
    frontend 640x480 overlay canvas (no scaling skew, no drift)."""
    if img.shape[1] == FRAME_W and img.shape[0] == FRAME_H:
        return img
    return cv2.resize(img, (FRAME_W, FRAME_H), interpolation=cv2.INTER_LINEAR)


def _strict_faces(gray_640: np.ndarray):
    """Raw Haar hits with strict criteria + aspect-ratio gate.

    - minNeighbors=6: only strong, repeatable face patterns survive
      (door frames / arches / wallpaper blobs rarely repeat 6x).
    - minSize=80x80: background wall artifacts are too small at 640x480.
    - aspect 0.7-1.3: faces are roughly square; tall thin arches fail.
    Returns list of (x, y, w, h) ints, largest-first.
    """
    if face_cascade is None:
        return []
    try:
        hits = face_cascade.detectMultiScale(
            gray_640,
            scaleFactor=DET_SCALE_FACTOR,
            minNeighbors=DET_MIN_NEIGHBORS,
            minSize=DET_MIN_SIZE,
        )
    except Exception:
        return []
    boxes = []
    for (x, y, w, h) in hits:
        if h <= 0:
            continue
        aspect = float(w) / float(h)
        if not (DET_ASPECT_LO <= aspect <= DET_ASPECT_HI):
            continue  # e.g. vertical door arch -> reject
        boxes.append((int(x), int(y), int(w), int(h)))
    boxes.sort(key=lambda b: b[2] * b[3], reverse=True)  # foreground first
    return boxes


def _confidence_for_box(w: int, h: int) -> float:
    """Haar gives no score: synthesize from relative face area at 640x480.
    Larger (closer/foreground) faces score higher; clamp to [0.80, 0.99]."""
    area_ratio = (w * h) / float(FRAME_W * FRAME_H)
    return round(min(0.99, 0.80 + area_ratio * 2.5), 2)


def detect_faces_jpeg(jpeg_bytes: bytes):
    """High-precision detect on canonical 640x480 frame.

    Returns [{type, confidence, bbox}] with bboxes in 640x480 space.
    """
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return []
    canon = _to_canonical(img)
    gray = cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY)
    out = []
    for (x, y, fw, fh) in _strict_faces(gray):
        out.append({"type": "face", "confidence": _confidence_for_box(fw, fh),
                    "bbox": [x, y, fw, fh]})
    return out


def annotate_frame(jpeg_bytes: bytes, dets: list) -> bytes:
    """Draw crisp neon-green (#00FF00) 2px boxes + filled label badges
    ("Name (conf)" / "Unknown Face (conf)") onto the canonical frame and
    return JPEG bytes ready to stream to the frontend."""
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return b""
    canon = _to_canonical(img)
    for d in dets:
        try:
            x, y, w, h = [int(v) for v in d["bbox"]]
        except Exception:
            continue
        cv2.rectangle(canon, (x, y), (x + w, y + h), NEON_GREEN_BGR, 2)
        label = d.get("label") or f"{d.get('name', 'face')} ({d.get('confidence', '')})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        y0 = max(0, y - th - 10)
        cv2.rectangle(canon, (x, y0), (x + tw + 8, y0 + th + 10), NEON_GREEN_BGR, -1)
        cv2.putText(canon, label, (x + 4, y0 + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", canon, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return bytes(buf) if ok else b""


def embedding_from_bgr(img: np.ndarray):
    """Lightweight CPU embedding: largest-face chip -> 64x64 gray, L2-normed.

    Deterministic + dependency-free (no torch/face_recognition needed inside
    Docker). Same person / same lighting => small Euclidean distance.
    Uses the strict largest face (foreground subject), not background blobs.
    Returns list[float] of length EMBED_SIZE*EMBED_SIZE.
    """
    canon = _to_canonical(img)
    gray = cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x, y, fw, fh = 0, 0, w, h
    try:
        faces = _strict_faces(gray)
        if len(faces):
            x, y, fw, fh = faces[0]  # largest strict face = foreground subject
            pad = int(0.15 * max(fw, fh))
            x, y = max(0, x - pad), max(0, y - pad)
            fw, fh = min(w - x, fw + 2 * pad), min(h - y, fh + 2 * pad)
    except Exception:
        pass
    chip = gray[y:y + fh, x:x + fw]
    if chip.size == 0:
        return None
    chip = cv2.resize(chip, (EMBED_SIZE, EMBED_SIZE))
    chip = cv2.equalizeHist(chip)  # lighting robustness for classroom projector light
    vec = chip.astype(np.float32).ravel() / 255.0
    n = float(np.linalg.norm(vec))
    if n < 1e-6:
        return None
    return (vec / n).tolist()


def embedding_from_bytes(jpeg_bytes: bytes):
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return None
    return embedding_from_bgr(img)


def embedding_for_bbox(jpeg_bytes: bytes, bbox):
    """Embedding for one detected box (bboxes live in canonical 640x480
    space; used by ReID per-face matching)."""
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return None
    canon = _to_canonical(img)
    try:
        x, y, fw, fh = [int(v) for v in bbox]
        h, w = canon.shape[:2]
        x, y = max(0, x), max(0, y)
        crop = canon[y:min(h, y + fh), x:min(w, x + fw)]
        if crop.size == 0:
            crop = canon
    except Exception:
        crop = canon
    return embedding_from_bgr(crop)


def _euclidean(a, b) -> float:
    try:
        return float(np.linalg.norm(np.array(a, dtype=np.float32) - np.array(b, dtype=np.float32)))
    except Exception:
        return float("inf")


def match_student(face_vec, students_rows):
    """Nearest-neighbour over stored mean embeddings. Returns (row, dist)|None."""
    best, best_d = None, float("inf")
    for s in students_rows:
        emb = s.embeddings or []
        if not emb:
            continue
        d = _euclidean(face_vec, emb)
        if d < best_d:
            best, best_d = s, d
    if best is not None and best_d <= REID_THRESHOLD:
        return best, round(best_d, 3)
    return None, None


def log_detections(dets: list):
    if not dets:
        return
    s = Session()
    try:
        s.add_all([DetectionEvent(detection_type=d.get("type", "face"),
                                  confidence=float(d.get("confidence", 0.9))) for d in dets])
        s.commit()
    except Exception:
        s.rollback()
    finally:
        s.close()


def _all_students():
    s = Session()
    try:
        return s.query(Student).all(), s  # caller closes
    except Exception:
        s.close()
        raise


# ============================================================================
# Auth (mock) + enrollment + attendance APIs
# ============================================================================
class LoginIn(BaseModel):
    username: str = ""
    password: str = ""
    role: str = ""  # optional hint: 'admin' | 'student'


@app.post("/api/auth/login")
def login(body: LoginIn):
    """Mock college SSO: admins contain 'admin'/'teacher', else student lookup."""
    u = (body.username or "").strip()
    hint = (body.role or "").lower()
    is_admin = hint == "admin" or u.lower().startswith("admin") or "teacher" in u.lower()
    if is_admin:
        return {"role": "admin", "name": "Class Teacher", "username": u or "admin"}
    # student path: match student_id or name
    s = Session()
    try:
        row = s.query(Student).filter(
            (Student.student_id == u) | (Student.name == u)).first()
        if row:
            return {"role": "student", "student_id": row.student_id,
                    "name": row.name, "branch": row.branch}
        # allow demo login even before enrollment (judges can type any ID)
        return {"role": "student", "student_id": u or "2100030001",
                "name": u or "Demo Student", "branch": "CSE", "guest": True}
    finally:
        s.close()


class EnrollIn(BaseModel):
    student_id: str
    name: str
    branch: str = "CSE"
    images: list = Field(default_factory=list,
                         description="4 base64 snapshots: Front, Left, Right, Up/Down")


@app.post("/api/students/enroll")
def enroll(body: EnrollIn):
    """4-angle onboarding: average per-angle embeddings -> one mean vector."""
    if not state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": state["phase"]}, status_code=503)
    sid = (body.student_id or "").strip()
    name = (body.name or "").strip()
    if not sid or not name or not body.images:
        raise HTTPException(status_code=422, detail="student_id, name and images[] required")
    vecs = []
    for i, b64 in enumerate(body.images[:8]):
        try:
            raw = decode_frame(b64)
        except HTTPException:
            raise HTTPException(status_code=422, detail=f"image[{i}] invalid base64")
        v = embedding_from_bytes(raw)
        if v is None:
            raise HTTPException(status_code=422, detail=f"image[{i}] has no usable face")
        vecs.append(np.array(v, dtype=np.float32))
    mean_vec = (sum(vecs) / len(vecs))
    n = float(np.linalg.norm(mean_vec))
    if n > 1e-6:
        mean_vec = mean_vec / n
    s = Session()
    try:
        row = s.query(Student).filter(Student.student_id == sid).first()
        if row:
            row.name, row.branch, row.embeddings = name, body.branch, mean_vec.tolist()
        else:
            row = Student(student_id=sid, name=name, branch=body.branch,
                          embeddings=mean_vec.tolist())
            s.add(row)
        s.commit()
        return {"ok": True, "student_id": sid, "name": name,
                "angles_used": len(vecs), "embedding_dim": len(mean_vec)}
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"enroll failed: {e}")
    finally:
        s.close()


@app.get("/api/students")
def list_students():
    s = Session()
    try:
        rows = s.query(Student).order_by(Student.student_id).all()
        return [{"student_id": r.student_id, "name": r.name, "branch": r.branch,
                 "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]
    finally:
        s.close()


class FrameIn(BaseModel):
    image: str  # "data:image/jpeg;base64,..." or raw base64


def _maybe_mark_present(student_row_id: str):
    """ReID safeguard: mark Present once per active session; repeats = no-op."""
    if active_session["id"] is None:
        return False
    key = (active_session["id"], student_row_id)
    with _session_lock:
        if key in marked_memory:
            return False
        marked_memory.add(key)
    s = Session()
    try:
        rec = s.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == active_session["id"],
            AttendanceRecord.student_id == student_row_id).first()
        if rec is None:
            rec = AttendanceRecord(session_id=active_session["id"],
                                   student_id=student_row_id, status="Present",
                                   marked_at=datetime.now())
            s.add(rec)
        elif rec.status != "Present":
            rec.status = "Present"
            rec.marked_at = datetime.now()
        else:
            return False  # already present in DB (e.g. after backend restart)
        s.commit()
        return True
    except Exception:
        s.rollback()
        with _session_lock:
            marked_memory.discard(key)
        return False
    finally:
        s.close()


def detect_and_identify(jpeg_bytes: bytes):
    """Full pipeline: strict detect -> per-face embed -> nearest student.

    Enriches each detection with {student_id, name, distance, label} where
    label is the server-side badge text: "Name (0.98)" for matches (which
    also logs an attendance_records row when a session is live) or
    "Unknown Face (0.9x)" otherwise. Returns enriched detections.
    """
    dets = detect_faces_jpeg(jpeg_bytes)
    if not dets:
        return dets
    s = Session()
    try:
        students = s.query(Student).all()
    finally:
        s.close()
    if not students:
        for d in dets:
            d.update({"student_id": None, "name": "Unknown Face",
                      "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
        return dets
    for d in dets:
        vec = embedding_for_bbox(jpeg_bytes, d["bbox"])
        if vec is None:
            d.update({"student_id": None, "name": "Unknown Face",
                      "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
            continue
        row, dist = match_student(vec, students)
        if row is not None:
            d.update({"student_id": row.student_id, "name": row.name,
                      "distance": dist,
                      "label": f"{row.name} ({d.get('confidence', '')})"})
            try:
                _maybe_mark_present(row.student_id)
            except Exception:
                pass
        else:
            d.update({"student_id": None, "name": "Unknown Face",
                      "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
    return dets


@app.post("/api/detect")
def detect_rest(frame: FrameIn):
    # Backwards-compatible: old UI polls this every 700ms; now also ReIDs.
    if not state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": state["phase"]}, status_code=503)
    raw = decode_frame(frame.image)
    dets = detect_and_identify(raw)
    log_detections(dets)
    return {"detections": dets, "active_session": dict(active_session)}


@app.post("/api/detect/annotated")
def detect_annotated(frame: FrameIn):
    """Server-side annotated stream frame: strict detect + ReID + neon-green
    (#00FF00) 2px boxes with "Name (conf)" badges drawn onto the canonical
    640x480 output frame. Returns {detections, image (data URL), size} so the
    frontend can render the processed stream pixel-perfect with no overlay
    skew. Purely additive — /api/detect behaviour is unchanged."""
    if not state["model_ready"]:
        return JSONResponse({"error": "model loading", "phase": state["phase"]}, status_code=503)
    raw = decode_frame(frame.image)
    dets = detect_and_identify(raw)
    log_detections(dets)
    annotated = annotate_frame(raw, dets)
    data_url = ("data:image/jpeg;base64," + base64.b64encode(annotated).decode()
                if annotated else None)
    return {"detections": dets, "image": data_url,
            "size": {"w": FRAME_W, "h": FRAME_H},
            "active_session": dict(active_session)}


@app.websocket("/ws/detect")
async def detect_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if not state["model_ready"]:
                await ws.send_json({"error": "model loading", "phase": state["phase"]})
                continue
            raw = decode_frame(msg.get("image", ""))
            dets = detect_and_identify(raw)
            log_detections(dets)
            await ws.send_json({"detections": dets, "active_session": dict(active_session)})
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await ws.close()
        except Exception:
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


# ------------------------- attendance sessions ------------------------------
class StartIn(BaseModel):
    session_name: str = "Morning Session"


@app.post("/api/attendance/start")
def attendance_start(body: StartIn):
    with _session_lock:
        if active_session["id"] is not None:
            raise HTTPException(status_code=409,
                                detail=f"session {active_session['id']} already active")
    s = Session()
    try:
        sess = AttendanceSession(session_name=body.session_name or "Session")
        s.add(sess)
        s.flush()  # get sess.id
        students = s.query(Student).all()
        for st in students:  # default Absent roster
            s.add(AttendanceRecord(session_id=sess.id, student_id=st.student_id,
                                   status="Absent", marked_at=None))
        s.commit()
        sid = sess.id
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"start failed: {e}")
    finally:
        s.close()
    with _session_lock:
        active_session.update({"id": sid, "name": body.session_name})
        marked_memory.clear()
    return {"ok": True, "session_id": sid, "session_name": body.session_name,
            "total_students": len(students) if 'students' in dir() else 0}


@app.post("/api/attendance/stop")
def attendance_stop():
    with _session_lock:
        sid = active_session["id"]
        if sid is None:
            raise HTTPException(status_code=409, detail="no active session")
        active_session.update({"id": None, "name": None})
        marked_memory.clear()
    return {"ok": True, "summary": session_summary(sid)}


def session_summary(sid: int):
    s = Session()
    try:
        recs = s.query(AttendanceRecord).filter(AttendanceRecord.session_id == sid).all()
        sess = s.query(AttendanceSession).filter(AttendanceSession.id == sid).first()
        present = [r for r in recs if r.status == "Present"]
        names = {r.student_id: "" for r in recs}
        for st in s.query(Student).all():
            if st.student_id in names:
                names[st.student_id] = st.name
        return {"session_id": sid,
                "session_name": sess.session_name if sess else "",
                "total": len(recs), "present": len(present),
                "absent": len(recs) - len(present),
                "records": [{"student_id": r.student_id, "name": names.get(r.student_id, ""),
                             "status": r.status,
                             "marked_at": r.marked_at.isoformat() if r.marked_at else None}
                            for r in sorted(recs, key=lambda r: r.student_id)]}
    finally:
        s.close()


@app.get("/api/attendance/roster")
def roster(session_id: int = None):
    sid = session_id if session_id is not None else active_session["id"]
    if sid is None:
        return {"session_id": None, "records": []}
    return session_summary(sid)


class OverrideIn(BaseModel):
    session_id: int
    student_id: str
    status: str  # Present | Absent


@app.post("/api/attendance/override")
def override(body: OverrideIn):
    if body.status not in ("Present", "Absent"):
        raise HTTPException(status_code=422, detail="status must be Present|Absent")
    s = Session()
    try:
        rec = s.query(AttendanceRecord).filter(
            AttendanceRecord.session_id == body.session_id,
            AttendanceRecord.student_id == body.student_id).first()
        now = datetime.now() if body.status == "Present" else None
        if rec is None:
            rec = AttendanceRecord(session_id=body.session_id, student_id=body.student_id,
                                   status=body.status, marked_at=now)
            s.add(rec)
        else:
            rec.status, rec.marked_at = body.status, now
        s.commit()
        with _session_lock:  # keep ReID memory consistent with manual edits
            key = (body.session_id, body.student_id)
            if body.status == "Present":
                marked_memory.add(key)
            else:
                marked_memory.discard(key)
        return {"ok": True, "session_id": body.session_id,
                "student_id": body.student_id, "status": body.status}
    except HTTPException:
        raise
    except Exception as e:
        s.rollback()
        raise HTTPException(status_code=500, detail=f"override failed: {e}")
    finally:
        s.close()


@app.get("/api/students/{student_id}/attendance")
def student_attendance(student_id: str):
    s = Session()
    try:
        row = s.query(Student).filter(Student.student_id == student_id).first()
        recs = (s.query(AttendanceRecord, AttendanceSession)
                .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
                .filter(AttendanceRecord.student_id == student_id)
                .order_by(AttendanceSession.id.desc()).all())
        total = len(recs)
        present = sum(1 for r, _ in recs if r.status == "Present")
        pct = round(present / total * 100, 1) if total else 0.0
        return {"student_id": student_id,
                "name": row.name if row else student_id,
                "branch": row.branch if row else "",
                "total_sessions": total, "present": present,
                "percentage": pct,
                "history": [{"session_id": sess.id, "session_name": sess.session_name,
                             "date": sess.date.isoformat() if sess.date else None,
                             "status": r.status,
                             "marked_at": r.marked_at.isoformat() if r.marked_at else None}
                            for r, sess in recs]}
    finally:
        s.close()
