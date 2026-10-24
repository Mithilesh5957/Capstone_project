FROM python:3.11-slim
WORKDIR /app

# libgl/libglib for OpenCV; libsm/libxext for MediaPipe/YOLO; curl for healthcheck
# NOTE: libgl1-mesa-glx is obsolete on Debian trixie (replaced by libgl1);
# libgl1 is installed instead to satisfy the same GL requirement.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libsm6 libxext6 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-warm YOLOv8 weights into the image layer so MARP
# LOADING_WEIGHTS does not hang on first download at runtime.
# yolov8n.pt is a guaranteed Ultralytics asset (caches torch + hub);
# yolov8n-face.pt is the project face model — best-effort cache, runtime
# FaceDetector falls back to MediaPipe/Haar if the file is absent.
RUN python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')" && \
    python -c "from ultralytics import YOLO; YOLO('yolov8n-face.pt')" || \
    echo "face-weights pre-warm skipped (lazy-load at runtime via YOLO_WEIGHTS)"

COPY app/ ./app/
COPY main.py .

ENV DATABASE_URL=postgresql://analytics:analytics@db:5432/analytics \
    MODEL_LOAD_SECONDS=15

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
