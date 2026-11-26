# FACEATTEND — Product Specification (Provisional Baseline)

**Status:** PROVISIONAL — no authoritative college specification was found in
the repository (searched all tracked files for specification, acceptance
criteria, problem statement, FR-/NFR- references; none exist). Every numeric
target below is marked `TBD — requires specification/owner approval` unless it
is already enforced by the implementation and its tests. Candidate values are
labeled `CANDIDATE` and are not requirements.
**Identifier scheme:** `FR-` functional, `SEC-` security, `NFR-` non-functional
(reliability/usability/maintainability/performance/accessibility/deployability),
`DATA-` data-handling/privacy, `OPS-` operations/startup/recovery, `UI-`
interface expectations. No prior ID scheme exists in the repo; this document
establishes it.
**Verification:** each requirement names a method: a test file/test name, an
endpoint probe, or `REVIEW` (code/document inspection). `TBD` marks undecided
measurement.

## 1. Purpose and users

FACEATTEND is a classroom face-attendance system: an operator enrolls students
with face samples, opens an attendance session, and students are marked
Present automatically as a camera feed recognizes them; records are viewable,
correctable, and exportable. Intended users: (a) **operator** (teacher/admin)
running enrollment, live sessions, corrections, exports, and health/chaos
controls; (b) **student** viewing their own attendance record.

## 2. Scope

**In scope:** operator/student JWT login; student enrollment (face images →
template); session lifecycle (start/stop/roster/summary); live WebSocket
recognition with dedup marking; manual override; CSV export; per-student
history; MARP health/readiness/telemetry; chaos drills; Docker Compose
dev/prod operation; documented K8s manifests (aspirational — see OPS gaps).
**Explicitly excluded:** real-time alerts/notifications; timetable or LMS
integration; biometric liveness/anti-spoof; multi-camera or distributed
deployment; automatic retraining or model management UI; mobile apps;
single-sign-on beyond local JWT.

## 3. Roles

- **Operator** (`role == "admin"`): full access — enrollment, sessions,
  overrides, exports, chaos, telemetry, settings, all records.
- **Student** (`role == "student"`): login with provisioned password; read
  only their own attendance record. Must never reach operator functions
  (enforced server-side; verified by `test_student_token_forbidden_*`).
- **Anonymous**: login and liveness/readiness probes only.

## 4. Functional requirements

- **FR-01** Operator login with username + password returns a signed JWT;
  wrong credentials → 401; unprovisioned admin → 503. *Tests:
  `test_r1_security.py::test_admin_login_success_and_password_verified`,
  `test_production_bootstrap_fails_closed`.*
- **FR-02** Student login requires a provisioned `users` row
  (`username == student_id`, `role == "student"`) and verifies the password;
  record existence alone never yields a token. *Tests: `test_student_login_matrix`.*
- **FR-03** Admin-only student-password provisioning for existing student
  records; unknown student → 404; role collision → 409; never overwrites other
  identities. *Tests: `test_student_login_matrix`,
  `test_provision_cannot_overwrite_admin_identity`.*
- **FR-04** Enrollment (admin, model-ready) accepts 1–8 face images, stores a
  normalized mean template, returns `embedding_dim`. Invalid images → 422;
  loading model → 503. *Test: `test_authorized_session_lifecycle` (CV
  stubbed); CV accuracy itself is UNVERIFIED — see FR-09.*
- **FR-05** Session lifecycle: start pre-creates `Absent` rows for all
  students; live frames mark `Present` exactly once per (session, student);
  stop returns a summary; roster/sessions list records. *Tests: R1 lifecycle
  test; R2 startup/recovery tests.*
- **FR-06** Manual override sets Present/Absent for one record; invalid status
  → 422; admin only. *Test: R1 lifecycle test.*
- **FR-07** CSV export of a session roster; admin only. *Test: R1
  `test_admin_logs_and_export_require_admin` (shape only). Content
  correctness vs roster: PARTIAL — byte-compare test missing.*
- **FR-08** Student self-service: read own record + history + percentage;
  other students' records → 403. *Tests: `test_student_can_read_own_record_only`.*
- **FR-09** Face pipeline: detector chain (YOLOv8-face → MediaPipe → Haar)
  with Haar fallback; raw-pixel template matching (64×64, L2, threshold 0.85,
  live-tunable). *Status: IMPLEMENTED as a baseline matcher; accuracy (FAR/
  FRR/latency) UNVERIFIED — no labelled evaluation dataset exists. Claimed
  "4096-d embeddings" are raw pixels, not learned embeddings (must be
  disclosed in academic documentation).*
- **FR-10** Telemetry events for lifecycle/chaos transitions + CSV export of
  stored rows (admin). *Status: PARTIAL — rows are dropped during DB outages
  by design; export shape tested, outage-loss documented.*

## 5. Security requirements

- **SEC-01** Every mutating/reading protected route enforces auth at the
  route boundary; no guarded handler is invocable without its `Depends`.
  *Tests: 40-route anonymous matrix + student-forbidden matrix (R1).*
- **SEC-02** No default credentials in production; dev bootstrap is explicit
  and warned; existing hashes never overwritten. *Tests: R1 bootstrap tests.*
- **SEC-03** Single authoritative JWT secret; production refuses
  missing/short/documented-default secrets at startup; tokens expire
  (default 24 h). *Tests: R1 secret tests + 1B startup matrix + lifespan
  refusal test.*
- **SEC-04** Forged/expired/malformed tokens rejected (401); privilege
  enforced per route (403). *Tests: R1 T2/T3.*
- **SEC-05** Deployment secrets never committed; prod values required via
  interpolation/Secret refs; populated secret files git-ignored. *Tests: 1B
  compose-render + K8s static checks. CANDIDATE: rotate demo secrets if ever
  exposed (no exposure found).*

## 6. Non-functional requirements

- **NFR-01 (reliability)** Boot is event-driven (DB check → bounded detector
  load); no fixed-delay readiness; single-flight loads; explicit FAILED
  states; operator-driven recovery; clean shutdown semantics. *Tests: 31 R2
  tests.* Numeric bound: attempt timeout `MODEL_LOAD_SECONDS` default 15 s —
  `TBD — requires specification/owner approval` as an SLO.
- **NFR-02 (usability)** Operator completes enroll → session → export without
  documentation; errors shown in-UI with 401/403 → re-login. *Method: REVIEW
  + manual walkthrough (no browser automation available — UNVERIFIED live).*
- **NFR-03 (maintainability)** Single backend entry, shared `*_impl` helpers,
  one shipped frontend entry; new code covered by tests. *Method: REVIEW.*
- **NFR-04 (performance)** No numeric SLO is approved. *CANDIDATE targets
  (not requirements): readiness p95 < 60 s on reference hardware; WS
  frame-to-mark p95 < 2 s; detect p95 < 800 ms/frame CPU. All TBD — require
  measurement on fixed hardware + dataset before adoption.*
- **NFR-05 (accessibility)** Keyboard-operable login/controls, visible focus,
  readable contrast, non-color-only status. *Method: manual checklist —
  UNVERIFIED; audit in the UI phase.*
- **NFR-06 (deployability)** `docker compose` dev works from `.env.example`;
  prod override fails closed without secrets; K8s manifests tracked without
  secrets. *Tests: 1B compose-render tests (parse-level, not a deploy
  proof). Full K8s deployability: NOT-IMPLEMENTED (missing DB/images/URL).*

## 7. Data-handling and privacy

- **DATA-01** Face templates stored as JSONB vectors linked to student_id;
  attendance records reference sessions/students with cascade delete.
  *Implemented; review schema.sql.*
- **DATA-02** Proposed (not confirmed obligations): collect explicit consent
  before enrollment; define retention window — `CANDIDATE: delete raw face
  images after template extraction; retain templates+records for one academic
  year` — TBD; provide student record-deletion endpoint (currently
  NOT-IMPLEMENTED — only Present/Absent override exists); log PII access.
  *All TBD — requires specification/owner + institutional policy approval.*
- **DATA-03** No raw face images are persisted by the backend (frames are
  processed in memory; enrollment stores derived vectors only). *Method:
  REVIEW (verified by inspection; add a test asserting no image persistence).*
- **DATA-04** Known limitation to disclose: photo-of-photo is accepted (no
  liveness/anti-spoof); pixel-template matching is lighting/pose sensitive.
  *Status: disclosed here; must appear in academic documentation.*

## 8. Error handling, health, startup, recovery, operations

- **OPS-01** Liveness = process alive (always 200); readiness = dependencies
  + model actually ready (200/503 with `failure_kind`). *Tests: R2 D-suite.*
- **OPS-02** Startup: secrets validated first; ENVIRONMENT explicit;
  DB-first check; bounded detector load; READY only on success. *Tests: 1B +
  R2 A-suite.*
- **OPS-03** Failure states are stable, structured (`failure_kind`, `phase`,
  `marp_state`), and recoverable via explicit operator action; post-ready DB
  flaps auto-recover. *Tests: R2 B/C/D suites.*
- **OPS-04** Shutdown refuses new work, invalidates in-flight attempts,
  bounds joins; hung inner detector work is documented as non-terminable
  (≤1 lingering daemon thread, commits nothing). *Tests: R2 E-suite.*
- **OPS-05** At most one live inner detector operation per process; a new
  load while one is hung fails fast `FAILED_BUSY` (restart clears a truly
  hung detector). *Tests: R2 gate tests.*

## 9. Interface and usability expectations

- **UI-01** Single shipped app (CRA `App.js`): login gate, hub dashboard,
  enrollment, live scanner, settings/chaos, student portal. *Implemented;
  polish UNVERIFIED — reserved for the UI phase, no style imposed here.*
- **UI-02** Every protected call sends `Bearer`; 401/403 returns to login
  with a message; no offline sessions; no hardcoded credentials. *Method:
  REVIEW (verified by inspection; browser execution UNVERIFIED — no tooling).*
- **UI-03** Loading/empty/error/success states for async operations; client
  CSV export matches displayed roster. *Status: PARTIAL (REVIEW).*
- **UI-04** Dead Vite tree (`App.jsx`, `pages/`, `components/`, `context/`,
  `api/`) is NOT shipped; its fate (delete vs promote) is an explicit open
  decision for the frontend phase (see DECISIONS.md D-09).

## 10. External dependencies and deployment assumptions

Postgres 15; Python 3.11 + pinned `requirements.txt` (numpy unpinned —
harden); Node 18 + CRA 5 for the shipped UI; YOLOv8/MediaPipe/Ultralytics
weights fetched at build/runtime (offline fallback: Haar/MediaPipe); Docker
Compose for dev + prod override; K8s manifests incomplete (no DB StatefulSet,
no published images, frontend URL strategy broken). No GPU required or used.

## 11. Unresolved questions (owner/specification input needed)

UQ-01 Official college specification/AC/KPI/FR/NFR targets (AC-1..4, KPI
targets, evaluation weights). UQ-02 Numeric SLOs (NFR-04 candidates). UQ-03
Privacy obligations (DATA-02: consent, retention, deletion, audit). UQ-04
Whether pixel-template baseline suffices for the capstone or a learned
embedding + measured evaluation is expected (FR-09). UQ-05 K8s: is a real
cluster deployable in scope, or is Compose the deployment target? UQ-06
Frontend: delete or promote the Vite tree (UI-04/D-09)? UQ-07 Production
hosting/staging environment for a deploy proof.
