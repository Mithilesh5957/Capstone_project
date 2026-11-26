# FACEATTEND — Candidate Verification Plan

How each area *should* be measured, with what data/environment, and where
results go. Nothing here has been executed unless the traceability matrix
says so. Numeric targets are TBD (SPEC UQ-01/UQ-02) — methods first, thresholds
after approval.

Results location: per-run artifacts under `experiments/<date>-<slug>/`
(JSON/CSV + `git rev-parse HEAD` + config redacted of secrets). Never invent
results.

## A. Authentication and authorization

- Method: TestClient matrix (existing `test_r1_security.py`, 78 tests):
  anonymous on all 40+ routes, student-on-admin, forged/expired/malformed
  JWTs, login matrix, provision matrix, WS 4401/4403 codes.
- Data/env: isolated Postgres, synthetic credentials only.
- Record: pytest output + `HASHER_MODE` line (proves real vs fallback KDF).

## B. Enrollment and attendance workflows

- Method: API-level lifecycle test (existing R1 test, CV stubbed) + browser
  walkthrough (login → enroll 4 angles → start → detect → stop → export) once
  tooling exists. Assert roster↔CSV byte-equality (test missing — add).
- Data: synthetic student IDs; snapshots of 4+ angles per subject.

## C. Detection and recognition quality

- Method: labelled evaluation set (NEEDS CREATION — `experiments/` + consent
  notes): N subjects × M conditions (lighting/angle/distance) + known
  non-matches. Report detection recall, ReID FAR/FRR vs threshold ROC,
  p50/p95 inference latency on reference CPU. Detection and identity metrics
  reported SEPARATELY. Presentation-attack trial disclosed (expect fail —
  no liveness).
- Do not use fake-detector orchestration tests as quality evidence.

## D. Startup, loading, timeout, recovery, shutdown

- Method: existing 31 R2 tests (fake loaders, event barriers, refused-engine
  DB) + real-DB integration tests. Fresh-DB repeat runs required.
- Record: stage/phase/kind transitions + attempt counts.

## E. Health checks and database availability

- Method: probe liveness/readiness codes + bodies during loading, ready,
  simulated DB loss, real connection failure (refused engine), recovery.
  Assert `failure_kind` vocabulary and legacy-key compatibility.

## F. Error handling and frontend feedback

- Method (R6 executed): `frontend/tests-browser/` on an isolated stack
  (Playwright 1.49 + Chromium + mocked API + live test backend; toolchain
  pinned in `frontend/tests-browser/requirements.txt`) — invalid
  login message, expired-token redirect to login, 403 handling, empty/error/
  loading states, real CSV download parsed and compared. See R6 report.

## G. API and database reliability

- Method: R1/R2 suites on isolated PG; compose healthcheck ordering observed
  in dev (`depends_on: service_healthy`); fault-injection harness ONLY against
  disposable stacks (never live services).

## H. Responsiveness, accessibility, browser compatibility, UI interaction

- Method (R6 executed on Chromium): 4-viewport no-overflow checks, modal
  fit, video aspect ratio, keyboard focus visibility, reduced-motion CSS,
  axe-core scan (0 critical/serious; moderates fixed and re-verified),
  non-color status cues. Screen-reader pass and second engine (Firefox/WebKit)
  remain manual/future — see R6 report.

## I. Performance, security, deployment reproducibility

- Performance: unmeasured — adopt SLOs first (NFR-04 candidates), then
  measure on fixed hardware. Security: R1 suite + secret sweeps
  (`grep` for deny-listed literals in tracked files). Reproducibility: clean
  `compose build` from committed files + `compose config` render checks
  (1B tests); image-digest pinning proposed, not done.

## J. Recording rule

Every executed check records: command, environment (Python/deps/DB), result
(pass/fail + counts), and artifacts. Static reviews are labeled REVIEW, never
converted into pass claims.
