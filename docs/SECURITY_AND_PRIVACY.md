# FACEATTEND Security and Privacy

What is enforced, what is assumed, and what remains an explicit owner decision.
No new obligations are invented here — open items point at the existing
trackers (UQ-03, DATA-02).

## Authentication and authorization (implemented, tested)

- JWT (`HS256`, `sub`/`role`/`iat`/`exp`, default TTL 24h) issued by
  `POST /api/v1/auth/login`; student logins additionally require a provisioned
  `users` row for an existing `students` record (record existence alone never
  yields a token). WebSockets authenticate via `?token=` (browsers cannot set
  WS headers): missing/invalid → `4401`, non-admin → `4403`.
- Every protected route enforces `require_admin` or `enforce_self_or_admin`
  server-side (anonymous matrix + student-forbidden matrix in
  `backend/tests/test_r1_security.py`). UI hiding is never the enforcement
  layer — the backend returns 401/403 and the client drops the session.
- Frontend sessions live in `localStorage` (`face_portal_session`) with no
  token → forced re-login; any 401/403 clears the session and returns to login.

## Secrets (fail-closed by design)

- `.env` is git-ignored and never committed; only `.env.example` (placeholders)
  is tracked. Production secrets arrive exclusively via environment
  interpolation (`docker-compose.prod.yml`) or out-of-band K8s Secrets
  (`k8s/*-secret.yaml` is git-ignored; only `*.example.yaml` is tracked).
- Missing/empty production secrets abort compose rendering; short or
  documented-default values (`default_dev_secret_change_me`, `admin123`,
  `change_me*`, weak/short strings) abort application startup with an explicit
  "Refusing to start" error. There is no silent fallback at any layer.
- Dev defaults (`admin123`, `analytics:analytics`, dev secret) exist only for
  local development and are greppable by design — CI asserts the production
  render contains none of them.
- Known hardening gaps (do not mistake for approval): CORS allows all origins
  (`app/main.py`); the backend Dockerfile bakes a weak dev `DATABASE_URL`
  (lowest precedence — override in real deployments); the dead Vite tree
  contains hardcoded demo credentials (`src/pages/Login.jsx`) — it is
  unshipped, but delete it (owner decision D-09) before any public release.

## Student data and biometrics

- Stored per student: `student_id`, name, branch, and one mean 4096-float
  normalized pixel template (JSONB). Raw face images are **never persisted**
  — frames are processed in memory; enrollment stores derived vectors only.
- Attendance links records to students via FK with cascading deletes.
- Telemetry stores no images or templates (phase/metrics/chaos knobs only,
  admin-exportable as CSV).
- **Undecided (owner + institutional policy required — UQ-03, DATA-02):**
  consent capture, retention windows, student record deletion (only override
  exists today), and PII access audit logging. **Do not onboard real student
  data until these are decided.** Test suites use synthetic IDs only
  (`2100030001`, `Stu Dent`); no biometric or production data was ever used
  in verification.

## Operational cautions

- Chaos endpoints (`/api/v1/marp/chaos/*`) deliberately break readiness —
  admin-only, intended for disposable stacks; never expose them to untrusted
  operators or production.
- Recognition has **no liveness/anti-spoofing**: photo-of-photo is accepted
  (disclosed limitation, not a vulnerability to "fix" without a plan).
- Logs: health/marp logs are operational; never log tokens, passwords,
  embeddings, or images. Database dumps and CSV exports contain PII — handle
  exports as personal data.
