FROM python:3.11-slim
WORKDIR /app

# libgl1/libglib2.0-0 for OpenCV; curl for the readiness healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    fastapi "uvicorn[standard]" "opencv-python-headless==4.10.0.84" numpy sqlalchemy psycopg2-binary

COPY main.py .

ENV DATABASE_URL=postgresql://analytics:analytics@db:5432/analytics \
    MODEL_LOAD_SECONDS=15

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
