"""R6-A authentication (mocked API) + live-backend authentication."""
import json

from conftest import (API_URL, WEB_URL, login_as, json_ok, stored_session,
                      stub_app_shell)


def test_login_renders_and_accepts_input(page):
    page.goto(WEB_URL)
    assert page.get_by_text("Face attendance sign in").is_visible()
    page.get_by_label("Username").fill("operator-x")
    page.get_by_label("Password", exact=True).fill("secret-x")
    assert page.get_by_label("Username").input_value() == "operator-x"


def test_successful_admin_login_uses_server_role(page):
    stub_app_shell(page)
    token = login_as(page, role="admin", username="op1", token="mock-admin-1",
                     name="Class Teacher")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    session = stored_session(page)
    assert session and session["token"] == token
    assert session["role"] == "Admin"  # server role, not the mode toggle
    assert page.get_by_text("Admin", exact=True).first.is_visible()


def test_wrong_credentials_show_error_and_no_session(page):
    page.route("**/api/auth/login",
               lambda r: r.fulfill(**json_ok({"detail": "invalid credentials"},
                                             status=401)))
    page.goto(WEB_URL)
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password", exact=True).fill("wrong")
    page.get_by_role("button", name="Login as").click()
    page.get_by_role("alert").wait_for(timeout=5000)
    assert "INVALID CREDENTIALS" in page.get_by_role("alert").inner_text()
    assert stored_session(page) is None


def test_network_failure_never_creates_session(page):
    page.route("**/api/auth/login", lambda r: r.abort())
    page.goto(WEB_URL)
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password", exact=True).fill("anything")
    page.get_by_role("button", name="Login as").click()
    page.get_by_role("alert").wait_for(timeout=8000)
    assert stored_session(page) is None


def test_expired_token_returns_to_login(page):
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-expired-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    # Simulate expiry: every subsequent roster poll is 401.
    page.unroute("**/api/attendance/roster*")
    page.route("**/api/attendance/roster*",
               lambda r: r.fulfill(**json_ok({"detail": "expired"}, status=401)))
    page.reload()
    page.get_by_text("Face attendance sign in").wait_for(timeout=10000)
    assert stored_session(page) is None


def test_protected_calls_carry_bearer_token(page):
    stub_app_shell(page)
    seen = {}

    def _capture(route):
        seen["auth"] = route.request.headers.get("authorization")
        route.fulfill(**json_ok([]))

    page.unroute("**/api/students")
    page.route("**/api/students", _capture)
    login_as(page, role="admin", token="mock-bearer-9")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    page.wait_for_timeout(6000)  # hub 5s poll must fire at least once
    assert seen.get("auth") == "Bearer mock-bearer-9", seen


def test_student_login_hides_admin_controls(page):
    stub_app_shell(page)
    page.route("**/api/students/2100030001/attendance",
               lambda r: r.fulfill(**json_ok(
                   {"student_id": "2100030001", "name": "Stu",
                    "branch": "CSE", "total_sessions": 0, "present": 0,
                    "percentage": 0.0, "history": []})))
    login_as(page, role="student", username="2100030001",
             token="mock-student-1", student_id="2100030001",
             name="Stu Dent", branch="CSE")
    page.get_by_text("Student portal").first.wait_for(timeout=8000)
    assert page.get_by_role("button", name="Students").count() == 0
    assert page.get_by_role("button", name="Settings").count() == 0
    assert page.get_by_text("Dashboard", exact=True).count() == 0


def test_logout_clears_session_and_returns_to_login(page):
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-logout-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    page.get_by_role("button", name="Log out").first.click()
    page.get_by_role("dialog").wait_for(timeout=5000)
    page.get_by_role("button", name="Stay signed in").click()
    assert stored_session(page) is not None  # cancel keeps the session
    page.get_by_role("button", name="Log out").first.click()
    page.get_by_role("button", name="Log out", exact=True).last.click()
    page.get_by_text("Face attendance sign in").wait_for(timeout=5000)
    assert stored_session(page) is None


def test_live_admin_login_and_empty_dashboard(page):
    """No mocks: real backend, real dev-seeded admin, empty disposable DB."""
    page.goto(WEB_URL)
    page.get_by_role("button", name="Admin", exact=True).click()
    page.get_by_label("Username").fill("admin")
    page.get_by_label("Password", exact=True).fill("R6TestAdminPass!")
    page.get_by_role("button", name="Login as").click()
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=15000)
    session = stored_session(page)
    assert session and session.get("token")
    assert session["role"] == "Admin"
    assert page.get_by_text("No sessions yet").count() >= 1
    # Real MARP status reaches the shell (backend Haar boots READY).
    page.get_by_text("MARP READY", exact=False).first.wait_for(timeout=20000)
