"""Face detection engine: YOLOv8-face -> MediaPipe -> Haar fallback + neon annotation.

READY is reached only after FaceDetector.load() finishes (called from
marp_engine.load_heavy_model). Strict Haar criteria on canonical 640x480 keep
foreground faces and reject door frames / wall noise.
"""
from __future__ import annotations
import base64
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
import cv2
import numpy as np
from fastapi import HTTPException
from ..core import config

Bbox = Tuple[int, int, int, int]


class FaceDetector:
    """Multi-tier detector with explicit state hooks."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.backend: str = "none"
        self.attempted: List[str] = []
        self.yolo = None
        self.mp = None
        self.haar = None
        self.load_ms: float = 0.0

    # -- loading chain ----------------------------------------------
    def load(self) -> bool:
        t0 = time.time()
        order = [b.strip().lower() for b in config.FACE_BACKEND_ORDER if b.strip()]
        for name in order:
            try:
                if name == "yolo" and self._load_yolo():
                    break
                if name == "mediapipe" and self._load_mediapipe():
                    break
                if name == "haar" and self._load_haar():
                    break
            except Exception:
                continue
        # Always ensure Haar exists as final safety net.
        if self.backend == "none":
            try:
                if self._load_haar():
                    pass
            except Exception:
                pass
        self.load_ms = (time.time() - t0) * 1000.0
        return self.backend != "none"

    def _load_yolo(self) -> bool:
        self.attempted.append("yolo")
        try:
            from ultralytics import YOLO  # type: ignore
        except Exception:
            return False
        try:
            model = YOLO(config.YOLO_WEIGHTS)
            with self._lock:
                self.yolo = model
                self.backend = "yolo"
            return True
        except Exception:
            return False

    def _load_mediapipe(self) -> bool:
        self.attempted.append("mediapipe")
        try:
            import mediapipe as mp  # type: ignore
            fd = mp.solutions.face_detection.FaceDetection(
                model_selection=1, min_detection_confidence=0.6)
            with self._lock:
                self.mp = fd
                if self.backend == "none":
                    self.backend = "mediapipe"
            return True
        except Exception:
            return False

    def _load_haar(self) -> bool:
        self.attempted.append("haar")
        cc = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if cc.empty():
            return False
        with self._lock:
            self.haar = cc
            if self.backend == "none":
                self.backend = "haar"
        return True

    # -- inference ----------------------------------------------------
    def detect(self, gray_640: np.ndarray) -> List[Bbox]:
        with self._lock:
            backend, yolo, mp, haar = self.backend, self.yolo, self.mp, self.haar
        if backend == "yolo" and yolo is not None:
            try:
                return self._detect_yolo(gray_640, yolo)
            except Exception:
                pass  # fall through to cheaper backends
        if (backend in ("mediapipe", "yolo")) and mp is not None:
            try:
                boxes = self._detect_mediapipe(gray_640, mp)
                if boxes:
                    return boxes
            except Exception:
                pass
        if haar is not None:
            return _haar_boxes(gray_640, haar)
        return []

    def _detect_yolo(self, gray_640: np.ndarray, model: Any) -> List[Bbox]:
        bgr = cv2.cvtColor(gray_640, cv2.COLOR_GRAY2BGR)
        res = model.predict(bgr, verbose=False, conf=0.5)
        boxes: List[Bbox] = []
        for r in res:
            for b in getattr(r, "boxes", []) or []:
                try:
                    x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
                    w, h = x2 - x1, y2 - y1
                    if h > 0 and _aspect_ok(w, h):
                        boxes.append((x1, y1, w, h))
                except Exception:
                    continue
        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        return boxes

    def _detect_mediapipe(self, gray_640: np.ndarray, fd: Any) -> List[Bbox]:
        bgr = cv2.cvtColor(gray_640, cv2.COLOR_GRAY2BGR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out = fd.process(rgb)
        boxes: List[Bbox] = []
        if not getattr(out, "detections", None):
            return boxes
        H, W = gray_640.shape[:2]
        for d in out.detections:
            try:
                bb = d.location_data.relative_bounding_box
                x, y = int(bb.xmin * W), int(bb.ymin * H)
                w, h = int(bb.width * W), int(bb.height * H)
                if h > 0 and _aspect_ok(w, h):
                    boxes.append((x, y, w, h))
            except Exception:
                continue
        boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
        return boxes


detector = FaceDetector()


def _aspect_ok(w: int, h: int) -> bool:
    if h <= 0:
        return False
    a = float(w) / float(h)
    return config.DET_ASPECT_LO <= a <= config.DET_ASPECT_HI


def _haar_boxes(gray_640: np.ndarray, cc: Any) -> List[Bbox]:
    try:
        hits = cc.detectMultiScale(
            gray_640, scaleFactor=config.DET_SCALE_FACTOR,
            minNeighbors=config.DET_MIN_NEIGHBORS, minSize=config.DET_MIN_SIZE)
    except Exception:
        return []
    boxes: List[Bbox] = []
    for (x, y, w, h) in hits:
        if h <= 0 or not _aspect_ok(int(w), int(h)):
            continue
        boxes.append((int(x), int(y), int(w), int(h)))
    boxes.sort(key=lambda b: b[2] * b[3], reverse=True)
    return boxes


# ---- legacy functional surface (delegates to singleton) ----
def decode_frame(data: str) -> bytes:
    if "," in data:
        data = data.split(",", 1)[1]
    try:
        return base64.b64decode(data, validate=True)
    except Exception:
        raise HTTPException(status_code=422, detail="invalid base64 image")


def _decode_bgr(jpeg_bytes: bytes):
    return cv2.imdecode(np.frombuffer(jpeg_bytes, np.uint8), cv2.IMREAD_COLOR)


def _to_canonical(img: np.ndarray) -> np.ndarray:
    if img.shape[1] == config.FRAME_W and img.shape[0] == config.FRAME_H:
        return img
    return cv2.resize(img, (config.FRAME_W, config.FRAME_H),
                      interpolation=cv2.INTER_LINEAR)


def _strict_faces(gray_640: np.ndarray):
    return detector.detect(gray_640)


def _confidence_for_box(w: int, h: int) -> float:
    area_ratio = (w * h) / float(config.FRAME_W * config.FRAME_H)
    return round(min(0.99, 0.80 + area_ratio * 2.5), 2)


def generate_boxes(gray_640: np.ndarray) -> List[Dict[str, Any]]:
    """Bounding-box generator with confidence (public intake hook)."""
    return [{"bbox": [x, y, w, h], "confidence": _confidence_for_box(w, h)}
            for (x, y, w, h) in detector.detect(gray_640)]


def crop_face_chip(bgr: np.ndarray, bbox: Bbox, size: int = 64) -> Optional[np.ndarray]:
    """Facial landmark cropping: pad 15%, clamp, resize (intake snapshots)."""
    try:
        x, y, w, h = [int(v) for v in bbox]
        H, W = bgr.shape[:2]
        pad = int(0.15 * max(w, h))
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(W, x + w + pad), min(H, y + h + pad)
        chip = bgr[y0:y1, x0:x1]
        if chip.size == 0:
            return None
        return cv2.resize(chip, (size, size))
    except Exception:
        return None


def detect_faces_jpeg(jpeg_bytes: bytes):
    from . import marp_engine as marp
    try:
        import random
        if random.random() < float(marp.chaos_knobs.get("frame_drop_rate", 0.0) or 0.0):
            return []
    except Exception:
        pass
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return []
    canon = _to_canonical(img)
    gray = cv2.cvtColor(canon, cv2.COLOR_BGR2GRAY)
    return [{"type": "face", "confidence": _confidence_for_box(fw, fh),
             "bbox": [x, y, fw, fh]} for (x, y, fw, fh) in detector.detect(gray)]


def annotate_frame(jpeg_bytes: bytes, dets: list) -> bytes:
    img = _decode_bgr(jpeg_bytes)
    if img is None:
        return b""
    canon = _to_canonical(img)
    for d in dets:
        try:
            x, y, w, h = [int(v) for v in d["bbox"]]
        except Exception:
            continue
        cv2.rectangle(canon, (x, y), (x + w, y + h), config.NEON_GREEN_BGR, 2)
        label = d.get("label") or f"{d.get('name', 'face')} ({d.get('confidence', '')})"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
        y0 = max(0, y - th - 10)
        cv2.rectangle(canon, (x, y0), (x + tw + 8, y0 + th + 10),
                      config.NEON_GREEN_BGR, -1)
        cv2.putText(canon, label, (x + 4, y0 + th + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1, cv2.LINE_AA)
    ok, buf = cv2.imencode(".jpg", canon, [cv2.IMWRITE_JPEG_QUALITY, 85])
    return bytes(buf) if ok else b""
