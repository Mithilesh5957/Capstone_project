# FACEATTEND — Decision Register

Confirmed decisions (with rationale) and open proposals. Proposals stay
proposals until approved — nothing here authorizes implementation.

## Confirmed

- **D-01 No default credentials in production.** Fail closed (503 + startup
  refusal) rather than seed `admin:admin123`. Rationale: college demo systems
  are probed; documented defaults are compromised by definition.
- **D-02 Single authoritative JWT secret** (`config.JWT_SECRET`, imported by
  `security.py`). Rationale: ended the divergent-default forgery risk.
- **D-03 Student credentials reuse the existing `users` table**
  (`username == student_id`, `role == "student"`); no schema migration.
  Rationale: backward-compatible; least schema churn for the security fix.
- **D-04 Explicit ENVIRONMENT contract** (development/test/production; anything
  else fails at import). Rationale: silent dev fallback caused the
  production-bypass blocker.
- **D-05 Compose dev/prod split** (base = explicit dev; `docker-compose.prod.yml`
  requires secrets). Rationale: dev convenience without prod foot-guns.
- **D-06 K8s Secret removed from tracked manifests**; operator creates it out
  of band. Rationale: secrets don't belong in git, even as "dev defaults".
- **D-07 Operator-driven recovery, no auto-retry** for MARP loads.
  Rationale: avoids retry storms and hidden flapping; failures stay visible.
- **D-08 Hung detector ⇒ FAILED_BUSY + process restart to clear.**
  Rationale: in-process threads cannot be killed; refusal bounds the damage
  to one lingering thread instead of silent accumulation.

## Scoped phase decisions

- **D-13 R4 canonical frontend = shipped CRA app (`src/index.js → App.js`,
  built by `docker build ./frontend` → nginx).** Rationale: verified from
  build config as the only served bundle; preserves auth contracts and
  working workflows with minimum regression risk. The Vite-oriented tree
  (`App.jsx`, `main.jsx`, `pages/`, `components/`, `context/`, `api/`) is
  explicitly legacy/unshipped for R4 and left untouched; its long-term fate
  (D-09 delete-vs-promote) remains deferred until the active app's build and
  functionality are verified, per the R4 stop condition.
- **D-14 Overlays portal to `document.body`; layout-affecting ancestors are
  out of scope for dialogs** (R6: a `space-y-*` margin leaked into the fixed
  backdrop, leaving a clickable strip). Rationale: portals isolate overlays
  from margin/transform/overflow/z-index contexts by construction.

## Open proposals (need owner approval)

- **D-09 Dead Vite tree fate:** (a) delete `App.jsx`/`main.jsx`/`pages/`/
  `components/`/`context/`/`api/` and keep CRA `App.js`; or (b) promote the
  modular tree and delete `App.js`. Recommendation: decide in the frontend
  phase after comparing testability; do not maintain both. (Blocks UI-04.)
- **D-10 CV direction:** keep pixel-template baseline with measured
  thresholds vs adopt a learned embedding (e.g., FaceNet/ArcFace-style) with
  a labelled evaluation. Needs UQ-04 answer + dataset cost estimate.
- **D-11 K8s scope:** full cluster deployment vs Compose-as-target. Needs
  UQ-05. Current manifests stay explicitly incomplete either way until then.
- **D-12 Telemetry persistence:** accept loss-during-outage vs add a
  bounded disk-backed buffer. Needs reliability requirements (UQ-01/02).
- **D-15 Pin the OpenCV pair (`opencv-python` + `opencv-contrib-python`) to one
  build (4.8.1.78) + NumPy 1.26.4; constrain
  transitive TypeScript to 4.x via `overrides`.** Rationale: unpinned
  resolution demonstrably broke in two ways — (a) numpy 2.x fails at import
  against opencv 4.8.1.78 (`numpy.core.multiarray`); (b) hoisted
  typescript@7 breaks react-scripts' `^3.2.1 || ^4` range so `npm ci`
  refuses. Pins are exact and minimal; no algorithm or API changes.

## Unresolved questions (from SPEC §11)

UQ-01 official spec/AC/KPIs; UQ-02 numeric SLOs; UQ-03 privacy obligations;
UQ-04 embedding sufficiency; UQ-05 K8s scope; UQ-06 Vite fate (= D-09);
UQ-07 staging environment.
