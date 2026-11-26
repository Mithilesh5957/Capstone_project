# FACEATTEND Testing Guide

What each suite proves, what it costs, and the exact commands. Evidence
vocabulary: a result counts only if the command exited 0 and is recorded —
report historical runs as historical.

## Backend (pinned py3.11 + isolated Postgres)

Needs: Python 3.11, a disposable Postgres, and the two pinned manifests:
`backend/requirements.txt` (production deps) and `backend/tests/requirements.txt`
(`pytest==9.1.1`, `httpx==0.27.2` — 0.28 removed the `TestClient(app=...)`
shortcut — and `PyYAML==6.0.3`). Test-only packages are deliberately excluded
from the production manifest.

```bash
# Disposable-database recipe (never point these at a live database):
docker network create t-net
docker run -d --name t-pg --network t-net \
  -e POSTGRES_PASSWORD=t-pw -e POSTGRES_DB=t_test postgres:15-alpine
export R1_TEST_DATABASE_URL="postgresql://postgres:t-pw@t-pg:5432/t_test"
# In a python:3.11 container with the backend mounted read-only:
pip install -r backend/requirements.txt -r backend/tests/requirements.txt
cd backend && python -m pytest tests/test_r1_security.py \
  tests/test_r2_marp.py tests/test_r7_dependencies.py \
  tests/test_roster_export.py tests/test_r9_matching.py \
  tests/test_r10_schema_concurrency.py tools/cv_eval/tests/test_cv_metrics.py
# Teardown: stop + remove the disposable container, network, and volume.
```

| File | Proves |
|---|---|
| `test_r1_security.py` (78) | auth bypass closed, no default creds, JWT handling, WS auth, startup-secret refusal |
| `test_r2_marp.py` (31) | deterministic startup, single-flight, bounded/busy failures, `failure_kind`s, shutdown |
| `test_r7_dependencies.py` | every requirement pinned; OpenCV pair shares one 4.8.1.78 build; no `headless`; NumPy 1.x |
| `test_roster_export.py` | roster ↔ CSV byte-equality incl. empty sessions |
| `test_r9_matching.py` (17) | vector validation, `<=` threshold rule, 1-NN selection, enroll 422s, dedup/unknown-face paths (synthetic vectors only — proves logic, not accuracy) |
| `test_r10_schema_concurrency.py` (5) | cross-process fresh-DB init via advisory lock, idempotency, failure visibility |
| `tools/cv_eval/tests/test_cv_metrics.py` (29) | metric arithmetic (IoU/PRF, FAR/FRR, ROC/AUC, EER, top-1, latency stats) — not accuracy |

Latest verified evidence: **169 passed, exit 0** (78+31+7+2+17+5+29).

## Configuration tests (host Python + docker CLI)

```bash
pytest backend/tests/test_1b_env_config.py   # 25 passed, exit 0
```

Covers the ENVIRONMENT contract, prod-secret matrix, and `docker compose
config` + K8s static checks (parse-level, not a deploy proof).

## Frontend

```bash
cd frontend && npm ci && npm run build   # committed lockfile; must stay green
```

## Browser (disposable r6-* stack, synthetic data only)

```bash
bash frontend/tests-browser/run.sh   # 59 passed, exit 0; tears itself down
```

What it is: real production build + Chromium, mostly **mocked API**
(`route.fulfill`) plus 2 **live-backend** login tests and R6-era live checks.
Mocked tests prove UI behavior, not backend integration or real-camera
detection. Locked selectors: the suite asserts exact labels/roles/text
(`Login as`, `Admin`/`Student`, `Live camera view`, `Settings & MARP chaos
hub`, `NO DETECTIONS YET`, `CAPTURE ALL 4 ANGLES…`, …) — do not rename tested
UI strings without updating the suite in the same change.

## CI (GitHub Actions, `main` push/PR)

Buildx → prod-override fail-closed check → compose build → CV import smoke
test → live stack → MARP READY poll → `fault_injection.py` → teardown.
CI status is not claimed in this repo — check the Actions tab.

## What is NOT covered

No labelled-dataset accuracy (FAR/FRR), no calibrated threshold, no staging
or production boot, no K8s deployment, no screen reader, no second browser
engine, no real-camera field test, no liveness evaluation. See
[REQUIREMENTS_TRACEABILITY.md](REQUIREMENTS_TRACEABILITY.md) and the R-series
reports in `audit-output/` for the per-requirement evidence map.
