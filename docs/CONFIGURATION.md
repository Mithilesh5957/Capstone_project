# FACEATTEND Configuration Reference

Single source of truth for every supported environment variable. Anything not
listed here is not read by the application.

## Core contract

| Variable | Required | Default / example | Notes |
|---|---|---|---|
| `ENVIRONMENT` | **yes** | `development` | Must be `development`, `test`, or `production`. Missing/blank/unknown refuses to boot at import. No silent fallback. |
| `DATABASE_URL` | prod: yes | `postgresql://analytics:analytics@db:5432/analytics` (dev) | SQLAlchemy URL. Sync `psycopg2` driver. The test suites override it per-run (`R1_TEST_DATABASE_URL`). |
| `JWT_SECRET` | prod: yes (≥32 chars, not a documented default) | `default_dev_secret_change_me` (dev only) | HS256 signing key. Single authoritative source (`core/config.py`). |
| `JWT_TTL_S` | no | `86400` | Token lifetime in seconds. |
| `ADMIN_USER` / `ADMIN_EMAIL` / `ADMIN_PASSWORD` | prod password: yes (≥12 chars, not `admin123`/documented) | `admin` / `admin@college.edu` / `admin123` (dev only) | Dev: auto-seeded on first login (stderr warning). Prod: never auto-seeded; startup validation fails fast otherwise. |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | prod password: yes | `analytics` / `analytics` / `analytics` (dev only) | Compose `db` service credentials. |

## Ports and URLs (compose)

| Variable | Default | Notes |
|---|---|---|
| `BACKEND_PORT` / `FRONTEND_PORT` | `8000` / `3000` | Host bindings. The `db` service publishes no host ports. |
| `VITE_API_URL` / `REACT_APP_API_URL` | `http://localhost:8000/api/v1` / `http://localhost:8000` | **Baked into the frontend bundle at build time** — changing them requires `docker compose build frontend`. (CRA reads only `REACT_APP_*`; `VITE_*` exists for the unshipped Vite tree.) |
| `REACT_APP_ORG_NAME` | *(empty → built-in fallback)* | White-label branding on the login screen. Build-time only; set in `.env`, then rebuild. Example: `REACT_APP_ORG_NAME=Your Institution` |

## Face pipeline

| Variable | Default | Notes |
|---|---|---|
| `FACE_BACKEND_ORDER` | `yolo,mediapipe,haar` | Detector chain; first backend that loads wins. Haar is the offline fallback. |
| `YOLO_WEIGHTS` | `yolov8n-face.pt` | `yolov8n.pt` is pre-warmed into the image; the face model downloads on first boot (~6 MB) unless cached. |
| `REID_THRESHOLD` | `0.85` | Accept iff Euclidean distance ≤ threshold. **Uncalibrated research default** — calibrate on labelled data before trusting it. Live-tunable via `POST /api/v1/settings/detection` (clamped `[0.1, 2.0]`, admin only). |
| `MODEL_LOAD_SECONDS` | `15` (dev service: `5`) | Per-attempt load **timeout bound**, not a wait. Fast loads go READY immediately. |
| `EMBED_SIZE` / `FRAME_W,H` | `64` / `640×480` | Template/canonical dimensions. Changing them invalidates stored templates. |

## Production (`-f docker-compose.prod.yml`)

Sets `ENVIRONMENT=production` literally and **requires** `JWT_SECRET`,
`ADMIN_PASSWORD`, `POSTGRES_PASSWORD`, `DATABASE_URL` via interpolation —
missing/empty values abort `config`/`up` before anything starts, and short or
documented-default values fail application startup. See
[Security](SECURITY_AND_PRIVACY.md). Validate without starting anything:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config
```

## Local development defaults

Everything unset falls back to documented local-only values (dev email,
`admin123`, `default_dev_secret_change_me`, `analytics:analytics`). These are
intentionally weak and greppable — CI asserts the production render contains
none of them. Never use them beyond localhost.
