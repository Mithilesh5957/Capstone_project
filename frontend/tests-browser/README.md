# R6 Browser QA — isolated stack & suite

Reproducible manual QA without touching live services.

## Stack (all disposable, synthetic test-only credentials)

```bash
docker network create r6-net
docker run --rm -d --name r6-pg --network r6-net \
  -e POSTGRES_PASSWORD=r6testpw -e POSTGRES_DB=r6test postgres:15-alpine
# Backend = working-tree code (read-only), pinned era deps (note the numpy pin:
# unpinned numpy 2.x breaks opencv 4.8 — real evidence for gap G-3.10).
docker run --rm -d --name r6-api --network r6-net -v "$PWD/backend:/app:ro" \
  -w /app -e ENVIRONMENT=development \
  -e DATABASE_URL="postgresql://postgres:r6testpw@r6-pg:5432/r6test" \
  -e MODEL_LOAD_SECONDS=15 \
  -e JWT_SECRET="r6-test-jwt-secret-0123456789abcdef" -e JWT_TTL_S=3600 \
  -e ADMIN_USER=admin -e ADMIN_PASSWORD="R6TestAdminPass!" \
  python:3.11-slim bash -c "pip install -q fastapi==0.104.1 'uvicorn[standard]==0.24.0.post1' sqlalchemy==2.0.23 psycopg2-binary==2.9.9 pydantic==2.5.2 psutil==5.9.6 'python-jose[cryptography]==3.3.0' 'passlib[bcrypt]==1.7.4' bcrypt==4.0.1 opencv-python-headless==4.8.1.78 'numpy==1.26.4' && python -m uvicorn main:app --host 0.0.0.0 --port 8000"
# Frontend production build pointed at the test API:
docker build ./frontend --build-arg REACT_APP_API_URL=http://r6-api:8000 \
  --build-arg VITE_API_URL=http://r6-api:8000/api/v1 -t r6-web:latest
docker run --rm -d --name r6-web --network r6-net r6-web:latest
# Browser tests (Playwright 1.49.0 + bound browsers):
docker run --rm --network r6-net -v "$PWD/frontend/tests-browser:/tests:ro" \
  mcr.microsoft.com/playwright/python:v1.49.0-jammy bash -c \
  "pip install -q 'playwright==1.49.1' pytest pytest-playwright requests 'psycopg[binary]' axe-core-python && cd /tests && python -m pytest . -q -p no:cacheprovider"
# Teardown (test containers only — never touch project-* containers/volumes):
docker stop r6-web r6-api r6-pg; docker network rm r6-net
```

Readiness gate before tests: poll
`http://r6-api:8000/api/v1/marp/healthz/readiness` until 200.

## What runs where

- `test_auth/test_dashboard/test_enroll/test_scanner/test_settings/test_portal/test_modal/test_csv/test_responsive_a11y`: **mocked API** (route.fulfill) + real browser + real production build. Prove UI behavior, not backend integration.
- `test_portal.py::test_live_*`, `test_auth.py::test_live_*`: **real backend** on the disposable stack (admin bootstrap, seeded student, real MARP status). Prove integration; CV paths stubbed/absent by design.
- No real credentials anywhere; all tokens are `mock-*` or test-only values.
