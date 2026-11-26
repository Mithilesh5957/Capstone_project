# FACEATTEND — Requirements Traceability Matrix

**Evidence vocabulary:** `IMPLEMENTED` / `UNIT-TESTED` / `INTEGRATION-TESTED` /
`STATICALLY-REVIEWED` / `UNVERIFIED` / `PARTIAL` / `NOT-IMPLEMENTED` /
`BLOCKED`. "Tested" means executed in this workspace (venv and/or pinned
production-dependency container); report-recorded claims are labeled as such.
Backend suite: 134 tests green (R1 78 + 1B 25 + R2 31).

| ID | Description | Source | Pri | Status | Implementation | Verification (executed unless noted) | Outstanding |
|---|---|---|---|---|---|---|---|
| FR-01 | Operator JWT login | README/docs | must | IMPLEMENTED + UNIT-TESTED | `auth_router.py:login`, `security.py` | `test_r1_security.py::test_admin_login_*`, `test_production_bootstrap_fails_closed` — executed | — |
| FR-02 | Password-verified student login | R1 design | must | IMPLEMENTED + UNIT-TESTED | `auth_router.py:login` student branch | `test_student_login_matrix` — executed | — |
| FR-03 | Admin provision-student (409 on collision) | R1/verification gate | must | IMPLEMENTED + UNIT-TESTED | `auth_router.py:provision_student` | `test_student_login_matrix`, `test_provision_cannot_overwrite_admin_identity` — executed | — |
| FR-04 | Enrollment 1–8 images → template | README | must | IMPLEMENTED, PARTIAL | `students_router.py:enroll_impl`, `face_recognition.py` | Contract/shape UNIT-TESTED (CV stubbed); recognition quality UNVERIFIED | labelled eval dataset; FAR/FRR |
| FR-05 | Session lifecycle + dedup marking | README/ARCHITECTURE | must | IMPLEMENTED + INTEGRATION-TESTED | `attendance_service.py`, `attendance_router.py` | R1 lifecycle test (isolated PG) — executed | concurrency-under-load test |
| FR-06 | Manual override | router | must | IMPLEMENTED + UNIT-TESTED | `attendance_router.py:override` | R1 lifecycle test — executed | — |
| FR-07 | CSV export | README/UI | must | IMPLEMENTED + UNIT-TESTED | `attendance_router.py:export_csv`, hub client CSV | R5 `test_roster_export.py`: export rows == roster records, header-only empty case — executed | hub client-side CSV parity by review only |
| FR-08 | Student self-service record | R1 design | must | IMPLEMENTED + UNIT-TESTED | `students_router.py:student_attendance` + self-or-admin | `test_student_can_read_own_record_only` — executed | — |
| FR-09 | Face detection + template ReID | README | must | IMPLEMENTED, PARTIAL | `face_detection.py`, `face_recognition.py` | Fallback chain UNIT-TESTED (imports only); accuracy UNVERIFIED | dataset + ROC/threshold calibration |
| FR-10 | Telemetry + CSV export | ARCHITECTURE | should | PARTIAL | `marp_engine.py:_log_telemetry_async`, `marp_router.py:telemetry_export` | Export shape reachable in tests; outage-loss by design (documented, untested live) | buffered telemetry (future) |
| SEC-01 | Route-boundary auth, no bypass | Phase-0 C1 | must | IMPLEMENTED + UNIT-TESTED | `main.py`, all routers | 40-route anon matrix + student-forbidden matrix — executed | — |
| SEC-02 | No default creds in prod | Phase-0 C2 | must | IMPLEMENTED + UNIT-TESTED | `auth_router.py:_ensure_admin`, `config.py` | R1 bootstrap tests — executed | — |
| SEC-03 | Single JWT secret + prod fail-fast | Phase-0 C3 | must | IMPLEMENTED + UNIT-TESTED | `config.py`, `security.py`, lifespan | R1 secret matrix + 1B lifespan refusal — executed | — |
| SEC-04 | Token/role enforcement | Phase-0 C4 | must | IMPLEMENTED + UNIT-TESTED | `security.py`, WS guards | R1 T2/T3 + WS 4401/4403 tests — executed | — |
| SEC-05 | Secrets handling in deploy | 1B report | must | PARTIAL | compose prod file, K8s Secret refs, `.gitignore` | 1B render/static checks — executed (parse-level, not a deploy proof) | staging deploy proof |
| NFR-01 | Deterministic startup/recovery | R2 report | must | IMPLEMENTED + UNIT-TESTED | `marp_engine.py` lifecycle | 31 R2 tests — executed (venv + prod container) | slow-network boot observation |
| NFR-02 | Usable operator flows | SPEC §6 | should | PARTIAL | `App.js` + `screens/` (login, hub, scanner, enroll, settings, portal) | R6: 59 browser tests green (mocked + live subsets); screen-reader not done | two-browser matrix, screen reader |
| NFR-03 | Maintainable structure | directive | should | STATICALLY-REVIEWED | routers/`*_impl`, single engine | Review only | lint/coverage gates (future) |
| NFR-04 | Performance SLOs | SPEC §6 | should | BLOCKED | — | No approved targets; candidates unmeasured | owner SLO decision + harness |
| NFR-05 | Accessibility | SPEC §6 | should | PARTIAL | `App.js` + `fa/` + `screens/` (labels, h1/landmarks, focus ring, trap, reduced-motion) | R6: axe 0 critical/serious/moderate on hub; keyboard + reduced-motion executed; screen reader NOT done | screen-reader pass, second browser engine |
| NFR-06 | Deployability | 1B report | must | PARTIAL | compose dev/prod, K8s manifests, pinned deps + lockfile | Config-render tests + `npm ci` + prod `docker build` executed (R7); K8s deploy NOT-IMPLEMENTED | staging proof; K8s DB/images/URL |
| DATA-01 | Template/record storage | schema.sql | must | IMPLEMENTED + STATICALLY-REVIEWED | `database/schema.sql`, models | Schema review; CRUD via tested flows | — |
| DATA-02 | Consent/retention/deletion/audit | SPEC §7 | must-decide | NOT-IMPLEMENTED | — | BLOCKED on UQ-03 | owner + institutional policy |
| DATA-03 | No raw image persistence | R3 design | should | STATICALLY-REVIEWED | `face_detection.py`, `face_recognition.py` | Code review only | persistence-absence test |
| DATA-04 | Spoof/lighting disclosure | Phase-0 | should | PARTIAL | SPEC §7 + this row | Disclosure written; academic docs pending | include in final report |
| OPS-01 | Liveness vs readiness | R2 report | must | IMPLEMENTED + UNIT-TESTED | `marp_engine.py:readiness`, probes | R2 D-suite — executed | — |
| OPS-02 | Startup contract | R2/1B reports | must | IMPLEMENTED + UNIT-TESTED | lifespan, `config.py`, worker | 1B + R2 A-suites — executed | — |
| OPS-03 | Stable failures + recovery | R2 report | must | IMPLEMENTED + UNIT-TESTED | worker, `reset_chaos`/`inject`/`recover` | R2 B/C suites — executed | — |
| OPS-04 | Shutdown semantics | R2 gate report | must | IMPLEMENTED + UNIT-TESTED | `note_shutdown`, lifespan | R2 E-suite — executed | — |
| OPS-05 | Hung-detector bound (≤1, FAILED_BUSY) | R2 gate report | must | IMPLEMENTED + UNIT-TESTED | slot in `_load_detector` | 9 gate tests — executed (venv + prod container) | process-restart runbook |
| UI-01 | Shipped CRA app screens | Phase-0 §9 | must | IMPLEMENTED, PARTIAL | All active screens restyled (R5); hub dead-branch removed | R6: 59 browser tests green on prod build (mocked + live subsets) | two-browser matrix, screen reader |
| UI-02 | Bearer auth + 401/403 handling | R1 report | must | IMPLEMENTED + INTEGRATION-TESTED | `fa/request.js` + screens | R6: login/logout/401/logout-flow/student-scoping executed in browser (mocked + live); backend rules unchanged (R1 suite) | two-browser matrix |
| UI-03 | Async states + export parity | SPEC §9 | should | PARTIAL | R5 restyle + R6: client CSV validated vs source incl. quoting/empty/failed-fetch; server CSV tested | R6 CSV tests executed (mocked data, real browser download+parse) | two-browser matrix |
| UI-04 | Dead Vite tree fate | Phase-0 | must-decide | NOT-IMPLEMENTED (decision) | `App.jsx`, `pages/`, etc. untouched by R5 (D-13 scoped CRA) | BLOCKED on D-09 | deletion/promotion decision |
| Official AC-1..4 / KPIs / college FR-NFR | college | must | BLOCKED | — | No spec found in repo | Cannot verify | obtain official spec (UQ-01) |

**Honesty notes:** (1) UI rows are review-only — no browser tooling exists in
this environment; (2) CV accuracy rows are UNVERIFIED — fakes prove
orchestration, never recognition quality; (3) deployability rows are
parse/config-level — no staging or production boot has been observed;
(4) DATA-02 and official acceptance rows are BLOCKED, not silently assumed.
