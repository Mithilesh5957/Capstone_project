# FACEATTEND — Gap Register and Roadmap

Gaps between the provisional SPEC and the current implementation, grouped and
sequenced by dependency. Mandatory vs desirable is marked per item.

## G-1 Release blockers / critical

1. **No official college specification** (UQ-01) — acceptance cannot be
   assessed. *Mandatory; unblocks everything evaluative.* Next: request spec.
2. **No staging/production boot proof** — config-level validation only.
   *Mandatory for any deploy claim.* Next: disposable staging stack.
3. **Privacy obligations undefined** (DATA-02: consent/retention/deletion/
   audit). *Mandatory before real student data.* Next: owner + policy decision.

## G-2 Core functional gaps

4. Student record-deletion endpoint missing (only override exists).
5. Roster↔CSV byte-equality test missing (FR-07 PARTIAL).
6. Dead Vite tree fate undecided (D-09/UI-04) — blocks coherent UI work.

## G-3 Test and evidence gaps

7. No browser/UI execution tests (NFR-02/UI-02 review-only).
8. No CV evaluation dataset or metrics (FR-09 UNVERIFIED).
9. Telemetry dropped during outages (accepted design; buffer is D-12).
10. RESOLVED in R7: numpy==1.26.4 + opencv pair pinned to 4.8.1.78
    (`backend/requirements.txt`); typescript constrained to 4.x via
    `overrides`; `frontend/package-lock.json` committed and `Dockerfile`
    uses `npm ci`. Remaining: image-digest pinning (G-7).

## G-4 CV and scientific gaps

11. Pixel-template baseline unmeasured (FAR/FRR/latency unknown); photo-spoof
    accepted (disclosed, unmitigated).
12. Threshold 0.85 uncalibrated (no ROC); MediaPipe short-range default
    untested at classroom distance.

## G-5 UI/UX and accessibility gaps

13. Active screens restyled (R5); 59-test Chromium browser suite green incl.
    keyboard trap, CSV, responsive, axe (R6); screen-reader pass, second
    browser engine, and full a11y audit remain (NFR-05).
14. Camera sliders: investigated in R5 — present only in the dead Vite tree,
    absent from the shipped app. No action unless the Vite tree is revived.
15. `SessionSummaryModal` export link: dead-tree component, not shipped.
    No action unless the Vite tree is revived. (Active-app CSV paths are
    authorized: `api()` bearer + client-side blob from roster data.)

## G-6 Deployment and operational gaps

16. K8s undeployable as shipped (no Postgres, no images, frontend URL).
17. Dockerfile bakes weak `DATABASE_URL` default (lowest precedence; harden).
18. Dev `MODEL_LOAD_SECONDS=5` vs prod 15 parity gap; offline weight-fetch behavior undocumented for air-gap demos.

## G-7 Future research/extensions (desirable, not mandatory)

Learned embeddings + measured comparison; buffered telemetry; bounded
auto-retry for DB-kind failures; per-backend detector sub-budgets; audit log
for PII access; image-digest pinning; CI browser smoke.

## Dependency-aware phase sequence (proposal)

1. **Spec & privacy decisions** (G-1: UQ-01/UQ-03) — owner input, no code.
2. **Frontend architecture** (D-09 → delete-or-promote Vite tree) — unblocks all UI work.
3. **UI polish + accessibility + browser tests** (G-5, NFR-02/05, G-7 items 14–15).
4. **CV evaluation** (dataset → ROC → threshold decision D-10; G-4, G-3.8).
5. **Deployability** (staging proof; K8s decision D-11; G-6).
6. **Research hardening** (telemetry buffer D-12, audit log, lockfiles; G-7).

Rule: phases start only after their decision inputs (UQ/D) are answered; no
phase claims completion without its traceability rows moving to tested states.
