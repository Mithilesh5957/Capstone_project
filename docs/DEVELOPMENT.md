# FACEATTEND Development Guide

Local development without touching production posture. All commands assume the
repository root unless noted.

## Prereqs

Docker Engine + Compose plugin, Git, a modern browser (Chromium for the
browser suite). ~4 GB free for images. First backend build downloads the
pinned Python stack including PyTorch (~2 GB, one time, cached).

## Fast path (verified pattern)

```bash
cp .env.example .env        # review it; dev defaults are LOCAL-ONLY
docker compose up -d --build
curl -i http://localhost:8000/api/v1/marp/healthz/readiness   # 503 → 200 READY
open http://localhost:3000 # admin login with your dev ADMIN_PASSWORD
docker compose logs -f backend   # watch MARP single-flight load
docker compose down              # stop; keeps the pgdata volume
```

A disposable variant (never your live stack): copy the `run.sh` pattern from
`frontend/tests-browser/` — separate network, database, and `r6-*` container
names, synthetic credentials, read-only source mount, self-teardown.

## Backend (no Docker)

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt -r backend/tests/requirements.txt
cd backend && ENVIRONMENT=test R1_TEST_DATABASE_URL="postgresql://…" \
  python -m pytest tests/ -q -p no:cacheprovider
```

Full pinned install is required for the CV import check
(`import cv2, numpy, app.services.face_detection, app.services.face_recognition`);
the app itself lazy-imports YOLO/MediaPipe with Haar fallback, so reduced
installs still boot (documented in `run.sh`, which pins only the CV/runtime
subset for speed).

## Frontend

```bash
cd frontend && npm ci && npm start        # dev server (CRA)
npm run build                             # production bundle (as shipped)
```

Build args (bake time!): `REACT_APP_API_URL`, `REACT_APP_ORG_NAME`. Changing
them requires a rebuild — see [Configuration](CONFIGURATION.md).

## Debugging

- Backend logs: `docker compose logs backend | grep -i "marp\|ready\|error"`.
- Readiness state machine: `GET /api/v1/marp/status` (admin JWT) shows phase,
  `marp_state`, `failure_kind`, chaos knobs, uptime, active session.
- Live readiness tail: `bash scripts/health_probe.sh http://localhost:8000 1`.
- DB shell (dev only): `docker compose exec db psql -U analytics analytics`.
- Frontend API target: check the built bundle or `REACT_APP_API_URL`.
- Common failures and fixes: [README](../README.md#troubleshooting).

## Conventions

- Locked UI strings: the browser suite asserts exact labels/roles/text — see
  [Testing](TESTING.md). Rename UI copy only together with its tests.
- New admin endpoints: `require_admin` + extend the R1 route matrix test.
- New chaos knob: add to `ChaosConfig` + allowlist + Settings UI with
  confirm-then-apply, mirroring existing knobs.
- No credentials, dumps, images, weights, or local artifacts in commits
  (see [Contributing](../CONTRIBUTING.md) and `.gitignore`).
