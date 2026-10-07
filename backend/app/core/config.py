"""FACEATTEND MARP — central configuration (env-driven, no hardcoding)."""
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://analytics:analytics@db:5432/analytics")
MODEL_LOAD_SECONDS = int(os.getenv("MODEL_LOAD_SECONDS", "15"))
REID_THRESHOLD = float(os.getenv("REID_THRESHOLD", "0.85"))
EMBED_SIZE = 64

FRAME_W, FRAME_H = 640, 480
DET_SCALE_FACTOR = 1.1
DET_MIN_NEIGHBORS = 6
DET_MIN_SIZE = (80, 80)
DET_ASPECT_LO, DET_ASPECT_HI = 0.7, 1.3
NEON_GREEN_BGR = (0, 255, 0)

JWT_SECRET = os.getenv("JWT_SECRET", "faceattend-dev-secret")
JWT_ALG = "HS256"
JWT_TTL_S = int(os.getenv("JWT_TTL_S", "86400"))

# YOLO / MediaPipe preferences (fallback chain is automatic)
YOLO_WEIGHTS = os.getenv("YOLO_WEIGHTS", "yolov8n-face.pt")
FACE_BACKEND_ORDER = os.getenv("FACE_BACKEND_ORDER", "yolo,mediapipe,haar").split(",")

# Chaos defaults (in-situ, no root required)
CHAOS_DEFAULTS = {
    "vram_latency_s": 0.0,
    "frame_drop_rate": 0.0,
    "model_stall": False,
    "simulated_latency_sec": 0.0,
    "simulate_vram_exhaustion": False,
    "artificial_probe_failure": False,
}
