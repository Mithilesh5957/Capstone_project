"""R6 browser suite — shared fixtures and helpers.

Topology (isolated, disposable): r6-pg (postgres) + r6-api (backend, dev mode,
synthetic creds) + r6-web (nginx serving the CRA production build with
REACT_APP_API_URL=http://r6-api:8000) + this Playwright container, all on
network r6-net. Live-backend tests use ONLY synthetic accounts/data.
"""
import json
import os

import pytest
from playwright.sync_api import sync_playwright

WEB_URL = "http://r6-web"
API_URL = "http://r6-api:8000"
# Direct-DB test access (isolated disposable database only). Defaults match
# run.sh's R6 stack; override per stack via the environment.
TEST_PG_DSN = os.environ.get(
    "TEST_PG_DSN", "postgresql://postgres:r6testpw@r6-pg:5432/r6test")

ADMIN_LOGIN = {"username": "admin", "password": "R6TestAdminPass!"}


@pytest.fixture(scope="session")
def pw_browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture()
def ctx(pw_browser):
    context = pw_browser.new_context(viewport={"width": 1280, "height": 720})
    yield context
    context.close()


@pytest.fixture()
def page(ctx):
    p = ctx.new_page()
    yield p
    p.close()


def json_ok(data, status=200):
    return {"status": status, "content_type": "application/json",
            "body": json.dumps(data)}


def stub_app_shell(page, *, status=None, readiness_code=200,
                   students=None, logs=None, sessions=None,
                   roster=None):
    """Default 200 fulfillments so background polls never 401 the session."""
    status = status if status is not None else {
        "phase": "ready", "marp_state": "READY", "stage": "READY",
        "model_ready": True, "db_connected": True, "uptime_s": 12.5,
        "active_session": {}, "chaos": {}, "metrics": {},
    }
    page.route("**/api/auth/login", lambda r: r.continue_())
    page.route("**/api/students", lambda r: r.fulfill(
        **json_ok(students if students is not None else [])))
    page.route("**/api/logs*", lambda r: r.fulfill(
        **json_ok(logs if logs is not None else [])))
    page.route("**/api/attendance/sessions*", lambda r: r.fulfill(
        **json_ok(sessions if sessions is not None else [])))
    page.route("**/api/attendance/roster*", lambda r: r.fulfill(
        **json_ok(roster if roster is not None else {"records": []})))
    page.route("**/api/v1/marp/status", lambda r: r.fulfill(**json_ok(status)))
    page.route("**/api/status", lambda r: r.fulfill(**json_ok(status)))
    page.route("**/api/v1/marp/healthz/readiness", lambda r: r.fulfill(
        **json_ok({"phase": "ready"}, status=readiness_code)))
    page.route("**/healthz/readiness", lambda r: r.fulfill(
        **json_ok({"phase": "ready"}, status=readiness_code)))


def login_as(page, role="admin", username="admin",
             token="mock-jwt-token", **extra):
    """Fulfill ONE login call, perform the UI login, return the token."""
    payload = {"role": role, "username": username, "token": token, **extra}

    def _fulfill(route):
        if route.request.method == "POST":
            route.fulfill(**json_ok(payload))
        else:
            route.continue_()

    page.route("**/api/auth/login", _fulfill)
    page.goto(WEB_URL)
    page.evaluate("() => localStorage.clear()")
    page.goto(WEB_URL)
    mode = "Admin" if role == "admin" else "Student"
    page.get_by_role("button", name=mode, exact=True).click()
    page.get_by_label("Username").fill(username)
    page.get_by_label("Password", exact=True).fill("irrelevant-secret-value")
    page.get_by_role("button", name="Login as", exact=False).click()
    return token


def stored_session(page):
    return page.evaluate(
        "() => JSON.parse(localStorage.getItem('face_portal_session') || 'null')")
