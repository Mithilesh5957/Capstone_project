"""CPU embedding + nearest-neighbour ReID (dependency-free, deterministic)."""
import cv2
import numpy as np
from ..core import config
from . import face_detection as fd
from . import marp_engine as marp


def embedding_from_bgr(img: np.ndarray):
    canon = fd._to_canonical(img)
    gray = cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    x, y, fw, fh = 0, 0, w, h
    try:
        faces = fd._strict_faces(gray)
        if faces:
            x, y, fw, fh = faces[0]
            pad = int(0.15 * max(fw, fh))
            x, y = max(0, x - pad), max(0, y - pad)
            fw, fh = min(w - x, fw + 2 * pad), min(h - y, fh + 2 * pad)
    except Exception:
        pass
    chip = gray[y:y + fh, x:x + fw]
    if chip.size == 0:
        return None
    chip = cv2.resize(chip, (config.EMBED_SIZE, config.EMBED_SIZE))
    chip = cv2.equalizeHist(chip)
    vec = chip.astype(np.float32).ravel() / 255.0
    n = float(np.linalg.norm(vec))
    if n < 1e-6:
        return None
    return (vec / n).tolist()


def embedding_from_bytes(jpeg_bytes: bytes):
    img = fd._decode_bgr(jpeg_bytes)
    return embedding_from_bgr(img) if img is not None else None


def embedding_for_bbox(jpeg_bytes: bytes, bbox):
    img = fd._decode_bgr(jpeg_bytes)
    if img is None:
        return None
    canon = fd._to_canonical(img)
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


def euclidean(a, b) -> float:
    try:
        return float(np.linalg.norm(
            np.array(a, dtype=np.float32) - np.array(b, dtype=np.float32)))
    except Exception:
        return float("inf")


def match_student(face_vec, students_rows):
    best, best_d = None, float("inf")
    for s in students_rows:
        emb = s.embeddings or []
        if not emb:
            continue
        d = euclidean(face_vec, emb)
        if d < best_d:
            best, best_d = s, d
    if best is not None and best_d <= config.REID_THRESHOLD:
        return best, round(best_d, 3)
    return None, None


def detect_and_identify(jpeg_bytes: bytes):
    from ..core.database import SessionLocal
    from ..models.student import Student
    from .attendance_service import maybe_mark_present
    dets = fd.detect_faces_jpeg(jpeg_bytes)
    if not dets:
        return dets
    s = SessionLocal()
    try:
        students = s.query(Student).all()
    finally:
        s.close()
    if not students:
        for d in dets:
            d.update({"student_id": None, "name": "Unknown Face", "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
        return dets
    for d in dets:
        vec = embedding_for_bbox(jpeg_bytes, d["bbox"])
        if vec is None:
            d.update({"student_id": None, "name": "Unknown Face", "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
            continue
        row, dist = match_student(vec, students)
        if row is not None:
            d.update({"student_id": row.student_id, "name": row.name, "distance": dist,
                      "label": f"{row.name} ({d.get('confidence', '')})"})
            try:
                maybe_mark_present(row.student_id)
            except Exception:
                pass
        else:
            d.update({"student_id": None, "name": "Unknown Face", "distance": None,
                      "label": f"Unknown Face ({d.get('confidence', '')})"})
    _ = marp  # keep marp import live for chaos knobs
    return dets


def log_detections(dets: list):
    if not dets:
        return
    from ..core.database import SessionLocal
    from ..models.detection import DetectionEvent
    s = SessionLocal()
    try:
        s.add_all([DetectionEvent(detection_type=d.get("type", "face"),
                                  confidence=float(d.get("confidence", 0.9)))
                   for d in dets])
        s.commit()
    except Exception:
        s.rollback()
    finally:
        s.close()
