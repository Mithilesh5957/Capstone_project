# FACEATTEND — Edge AI Face Attendance with MARP

Enterprise-grade face-recognition attendance for classrooms: FastAPI + PostgreSQL backend with a **Model-Aware Readiness Protocol (MARP)**, in-situ chaos engineering, WebSocket live roll call, and a high-contrast Neo-Brutalist React UI.

| Layer | Stack |
|---|---|
| AI core | YOLOv8-face → MediaPipe → Haar fallback (OpenCV 640×480), CPU embedding (64×64 L2-norm), nearest-neighbour ReID |
| Backend | FastAPI, SQLAlchemy, `python-jose` JWT + `passlib/bcrypt`, `psycopg2` |
| DB | PostgreSQL 15 (`students`, `attendance_sessions`, `attendance_records`, `detection_events`, `users`, `marp_telemetry`) |
| Frontend | React (CRA build, Vite env compat), Tailwind, `#E2FF00` neon / `#F4F4F0` paper, `.brutal-card` / `.brutal-btn` |
| Edge/Cloud | Docker Compose (prod + `development` profile), Kubernetes (MARP probes), GitHub Actions CI + AC-2 fault injection |

## Architecture Overview

```
 webcam ──JPEG base64──▶ /api/v1/attendance/ws/detect?token=JWT ──▶ process_live_frame()
        │                         │ ack {detections, newly_marked} (backpressure: next frame only after ack/1s)
        │                         ▼
        │              face_detection (YOLO→MP→Haar) → face_recognition (ReID, threshold 0.85)
        │                         ▼ marked_memory dedup
        └──────────◀── canvas overlay (640×480 canonical → video size) + live roll call
Postgres: attendance_records (Present once per session) + detection_events + marp_telemetry (STATE_CHANGE/CHAOS_*)
MARP:   UNINITIALIZED → LOADING_WEIGHTS → READY (503 until READY, 200 after; FAILED_{DB,MODEL,TIMEOUT} distinct, SHUTDOWN terminal)
```

Key flows:
- **Enroll:** `POST /api/v1/students/enroll` (admin JWT) — 1–8 face images → mean L2 embedding → upsert `students`.
- **Session:** `POST /attendance/start` pre-creates `Absent` rows; live WS marks `Present` once via `marked_memory`; `POST /attendance/stop` returns summary; `GET /export.csv` downloads roster.
- **Research:** every MARP transition / chaos inject fires async `marp_telemetry` insert; `GET /api/v1/marp/telemetry/export` (admin JWT) returns flattened `marp_research_data.csv`.

## The MARP Protocol (race condition it solves)

Standard Uvicorn/K8s deployments route traffic the moment the socket opens — **before** AI weights are in VRAM. The result: dropped frames, half-loaded detectors, and flaky 500s during the ~24s YOLOv8/MediaPipe warmup.

MARP makes readiness model-aware:
- Boot runs in background (`lifespan → start_background_load → single-flight load attempt`): real DB check first (`create_all` + `SELECT 1`, `db_failed` on error) → bounded detector-chain init → `READY` with `model_load_duration_ms` + `vram_allocated_mb`. No fixed startup sleep: `MODEL_LOAD_SECONDS` is the per-attempt timeout bound (plus intentional chaos delays), so fast loads go READY immediately while genuinely stalled loads end in an explicit `FAILED_TIMEOUT`.
- `GET /api/v1/marp/healthz/readiness` returns **503** with `{marp_state: LOADING_WEIGHTS|FAILED_DB|FAILED_MODEL|FAILED_TIMEOUT|..., failure_kind: loading|db|model|timeout|shutdown}` until `model_ready && db_ready`, then **200** `{marp_state: READY}`. Failures are stable until explicit recovery (`recover`/`reset` starts one new single-flight attempt; concurrent callers attach to the running one).
- K8s `readinessProbe` and Compose `healthcheck` poll this endpoint (`failureThreshold: 30`, `periodSeconds: 5`), so Endpoints stay empty until VRAM is hot — zero dropped camera frames.
- Chaos knobs (`simulate_vram_exhaustion`, `artificial_probe_failure`, `model_stall`, latency/drop rates) force 503 on demand to prove failover; `reset_chaos` triggers `reloading` → background reload → 200 without restart (AC-2).

## In-Situ Chaos Engineering

No root, no sidecars — all via API (admin JWT) and UI panel:
| Knob | Effect |
|---|---|
| `simulated_latency_sec` / `vram_latency_s` | stalls readiness probe + boot sleep (failover drill) |
| `frame_drop_rate` | randomly drops `detect_faces_jpeg` frames |
| `artificial_probe_failure` | forces readiness 503 `FAILED_PROBE` |
| `simulate_vram_exhaustion` | forces 503 `FAILED_VRAM`, fails boot |
| `model_stall` | holds `LOADING_WEIGHTS` up to the load budget, then `FAILED_TIMEOUT` (releasable early by clearing the knob) |
| `db_drop` / `model_unload` / `recover` | legacy `SIMULATED_*` flags → 503 → reload → 200 |

Validate: `python tests/fault_injection.py` kills `db` mid-load, asserts 503 while down, 200 after reboot without backend restart, and reports KPI-4 (recovery time) + KPI-6 (latency impact) to JSON/CSV.

## Neo-Brutalist UI

Design tokens: `neon #E2FF00`, `paper #F4F4F0`, `border-4 black`, `shadow-[8px_8px_0px]`, `Space Grotesk` + mono. Primitives `.brutal-card`, `.brutal-btn`, `.brutal-input` (+ `nb-*` compat). Pages: Login (admin/student), Dashboard (sessions, distribution, export), Students (enroll), Attendance (WS live view + `brutal-card` live roll call with `bg-[#E2FF00]` highlight + canvas boxes), Settings (MARP chaos hub + `EXPORT TELEMETRY (CSV)` + terminal log).

## Quickstart (Docker Compose)

The app selects its security posture from `ENVIRONMENT` (`development` | `test`
| `production`). Missing, blank, or unsupported values refuse to boot — there
is no silent fallback. Development and production use separate configurations.

```bash
# ---- A. local development (explicit dev mode, local-only defaults) ----
cp .env.example .env   # review; dev defaults in .env work for local use only
docker compose up -d --build
# dev live-reload backend instead:
docker compose --profile development up -d --build
# ---- B. production (explicit prod mode, externally supplied secrets) ----
export JWT_SECRET="$(openssl rand -hex 32)"
export ADMIN_PASSWORD='<strong password, at least 12 chars>'
export POSTGRES_PASSWORD='<strong database password>'
export DATABASE_URL="postgresql://analytics:${POSTGRES_PASSWORD}@db:5432/analytics"
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# Missing/empty required secrets abort `config`/`up` before anything starts;
# short or documented-default values additionally fail application startup.
```

```bash
# 1. watch MARP warm up: 503 LOADING_WEIGHTS → 200 READY
curl -i http://localhost:8000/api/v1/marp/healthz/readiness
# 2. login + start session (use the ADMIN_PASSWORD you configured —
#    never the documented development defaults)
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"admin\",\"password\":\"$ADMIN_PASSWORD\",\"role\":\"admin\"}" | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")
curl -X POST localhost:8000/api/v1/attendance/start -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"session_name":"Morning Session"}'
# 3. frontend
open http://localhost:3000  # admin login → Attendance → START CAMERA (WS ?token=JWT, ack-or-1s backpressure)
# 4. research export
curl -H "Authorization: Bearer $TOKEN" \
  localhost:8000/api/v1/marp/telemetry/export -o marp_research_data.csv
```

K8s: create `faceattend-backend-secret` outside source control first (see
`k8s/backend-secret.example.yaml`), then `kubectl apply -f k8s/` (probes map to
MARP endpoints — see `ARCHITECTURE.md`). Note: K8s deployment is still
incomplete (no Postgres manifest, no published images, frontend API-URL
strategy unresolved) and is not production-ready. CI: push to `main` runs
Buildx → `compose up` → READY poll → `fault_injection.py`.
