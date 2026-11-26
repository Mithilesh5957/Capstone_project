# FACEATTEND Template Guide

How to adopt this repository for your own institution or project. This guide
assumes the README quickstart already works on your machine.

## 1. What you get

A working classroom face-attendance system: React 18 frontend, FastAPI +
PostgreSQL backend, a YOLOv8/MediaPipe/Haar detection chain with a
nearest-neighbour pixel-template matcher, MARP model-aware readiness, in-situ
chaos drills, telemetry export, and pinned reproducible dependencies with
117+ backend, 25 config, and 59 browser tests.

What travels with the template: all application code, Compose files,
example configs, docs, and tests. What does NOT travel: no database, no
credentials, no student records, no biometric images, no model weights
(weights download on first boot).

## 2. Adopt it in an afternoon

1. Fork or click **Use this template** (once the owner enables it — see
   [Contributing](../CONTRIBUTING.md); this step needs no code changes).
2. `git clone <your-fork-url> && cd <repo> && cp .env.example .env`
3. Review `.env` (dev defaults are local-only; see [Configuration](CONFIGURATION.md)).
4. `docker compose up -d --build`, then poll
   `http://localhost:8000/api/v1/marp/healthz/readiness` until 200.
5. Open `http://localhost:3000`, log in as `admin` (dev default from your
   `.env`), enroll a test subject, start a session, verify a mark, export CSV.
6. Run the test suites ([Testing](TESTING.md)) to establish your baseline.

## 3. Configure for your institution

| Area | How | File(s) |
|---|---|---|
| Branding (login screen) | Set `REACT_APP_ORG_NAME` (uncomment in `.env`), then `docker compose build frontend` (CRA bakes it at build time) | `.env.example`, `frontend/Dockerfile`, `LoginScreen.jsx` |
| API base URL in bundle | `REACT_APP_API_URL` / `VITE_API_URL` build args | `docker-compose.yml`, `.env.example` |
| Ports | `BACKEND_PORT`, `FRONTEND_PORT` | `.env` |
| Operator account | `ADMIN_USER`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` (≥12 chars, not a default) | `.env` + prod override |
| Email-domain login normalization | Edit the accepted-domain tuple | `backend/app/routers/auth_router.py` (`_canonical_identity`; defaults `college.edu`, `kluniversity.in`) |
| Branch/department list | Edit `BRANCHES` | `frontend/src/App.js` |
| Detection chain/backends | `FACE_BACKEND_ORDER`, `YOLO_WEIGHTS`, `MODEL_LOAD_SECONDS` | `.env` |
| Matching threshold | `REID_THRESHOLD` (default 0.85, **uncalibrated** — see Limitations) | `.env` |
| Secrets | Never in git; see [Security](SECURITY_AND_PRIVACY.md) | `docker-compose.prod.yml`, `k8s/*example*` |

## 4. Initialize the database

Fresh databases self-initialize: the `db` service applies
`database/schema.sql` on first boot (named volume `pgdata` persists it), and
the backend's idempotent `create_all` (cross-process serialized by a
PostgreSQL advisory lock) covers the rest. Verify with the readiness endpoint
(`db_ready: true`) before enrolling.

## 5. Extend safely

- New detector backend: implement `load()` + `detect()` in
  `face_detection.py`, append its name to `FACE_BACKEND_ORDER`. Haar must stay
  last as the offline safety net.
- New chaos knob: add to `ChaosConfig` + `apply_chaos` allowlist, surface it
  in `SettingsView` with the existing confirm-then-apply pattern.
- New admin endpoint: use `require_admin`; student-readable: use
  `get_current_user` + `enforce_self_or_admin`. Add it to the R1 route matrix
  test.
- New UI screen: add a tab entry + route in `App.js`, reuse `fa/` primitives
  and tokens only (see `docs/FRONTEND_DESIGN_SYSTEM.md`); do not rename
  existing accessible labels — the browser suite asserts them (locked list in
  [Testing](TESTING.md)).

## 6. What stays your responsibility

Consented data acquisition, retention/deletion policy, threshold calibration
on your labelled data, staging/production boot proof, K8s completion,
screen-reader pass, second browser engine, and license selection. None of
these ship with the template.
