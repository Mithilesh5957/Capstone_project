# R6 browser QA — isolated disposable stack (all synthetic test data).
#
# Prerequisites: docker with network + image pull access. Nothing here touches
# the live project containers, volumes, or databases: dedicated network
# (r6-net), dedicated Postgres, unpublished ports, synthetic credentials only.
#
#   1. network + disposable database
docker network create r6-net
docker run --rm -d --name r6-pg --network r6-net \
  -e POSTGRES_PASSWORD=r6testpw -e POSTGRES_DB=r6test postgres:15-alpine

#   2. backend from the working tree (read-only bind), pinned era deps.
#      TEST-ONLY credentials below (never real secrets).
docker run --rm -d --name r6-api --network r6-net \
  -v "$PWD/backend:/app:ro" -w /app \
  -e ENVIRONMENT=development \
  -e DATABASE_URL="postgresql://postgres:r6testpw@r6-pg:5432/r6test" \
  -e MODEL_LOAD_SECONDS=15 \
  -e JWT_SECRET="r6-test-jwt-secret-0123456789abcdef" \
  -e JWT_TTL_S=3600 -e ADMIN_USER=admin -e ADMIN_PASSWORD="R6TestAdminPass!" \
  python:3.11-slim bash -c "pip install --timeout 120 --retries 10 -q fastapi==0.104.1 'uvicorn[standard]==0.24.0.post1' sqlalchemy==2.0.23 psycopg2-binary==2.9.9 pydantic==2.5.2 psutil==5.9.6 'python-jose[cryptography]==3.3.0' 'passlib[bcrypt]==1.7.4' bcrypt==4.0.1 opencv-python-headless==4.8.1.78 'numpy==1.26.4' && python -m uvicorn main:app --host 0.0.0.0 --port 8000"

#   3. frontend production build pointed at the test API, served by nginx.
docker build ./frontend --build-arg REACT_APP_API_URL=http://r6-api:8000 -t r6-web:latest
docker run --rm -d --name r6-web --network r6-net r6-web:latest

#   4. wait for READY, then run the suite from the Playwright image.
docker run --rm --network r6-net curlimages/curl:8.5.0 -s --retry 12 --retry-all-errors \
  --retry-delay 5 http://r6-api:8000/api/v1/marp/healthz/readiness
docker run --rm --network r6-net \
  -v "$PWD/frontend/tests-browser:/tests:ro" \
  -e TEST_PG_DSN="postgresql://postgres:r6testpw@r6-pg:5432/r6test" \
  mcr.microsoft.com/playwright/python:v1.49.0-jammy bash -c \
  "pip install --timeout 120 --retries 10 -q -r /tests/requirements.txt && cd /tests && python -m pytest -q"

#   5. teardown (test containers only; live project stack untouched).
docker stop r6-web r6-api r6-pg; docker network rm r6-net
