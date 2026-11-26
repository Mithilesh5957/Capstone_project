"""R6-F student portal: data rendering, empty/error states, auth scoping."""
from conftest import json_ok, login_as, stored_session, stub_app_shell


def _portal(page, record=None, status=200):
    stub_app_shell(page)
    if record is not None:
        page.unroute("**/api/students/2100030001/attendance")
        page.route("**/api/students/2100030001/attendance",
                   lambda r: r.fulfill(**json_ok(record, status=status)))
    login_as(page, role="student", username="2100030001",
             token="mock-portal-1", student_id="2100030001",
             name="Stu Dent", branch="CSE")
    page.get_by_text("Student portal").wait_for(timeout=8000)


def test_portal_shows_personal_record(page):
    _portal(page, record={
        "student_id": "2100030001", "name": "Stu Dent", "branch": "CSE",
        "total_sessions": 2, "present": 1, "percentage": 50.0,
        "history": [
            {"session_id": 1, "session_name": "Morning", "date": "2026-01-01",
             "status": "Present", "marked_at": "2026-01-01T10:00:00"},
            {"session_id": 2, "session_name": "Lab", "date": "2026-01-02",
             "status": "Absent", "marked_at": None}]})
    assert page.get_by_text("Stu Dent").first.is_visible()
    # JS renders numeric 50.0 as "50".
    assert page.get_by_text("50%", exact=False).first.is_visible()
    assert page.get_by_text("Morning").is_visible()
    assert page.get_by_text("Present", exact=True).first.is_visible()
    assert page.get_by_role("button", name="Students").count() == 0
    assert page.get_by_role("button", name="Settings").count() == 0


def test_portal_empty_history_state(page):
    _portal(page, record={
        "student_id": "2100030001", "name": "Stu Dent", "branch": "CSE",
        "total_sessions": 0, "present": 0, "percentage": 0.0, "history": []})
    assert page.get_by_text("No attendance records yet.").is_visible()


def test_portal_401_returns_to_login(page):
    stub_app_shell(page)
    page.route("**/api/students/2100030001/attendance",
               lambda r: r.fulfill(**json_ok({"detail": "expired"},
                                             status=401)))
    login_as(page, role="student", token="mock-portal-exp",
             student_id="2100030001", name="Stu", branch="CSE")
    page.get_by_text("Face attendance sign in").wait_for(timeout=10000)
    assert stored_session(page) is None


def test_live_student_login_and_empty_portal(page):
    """No mocks: provision a real student, log in, see the portal."""
    import json as _json
    import urllib.request
    api = "http://r6-api:8000"

    def post(path, body, token=None):
        req = urllib.request.Request(
            api + path, data=_json.dumps(body).encode(),
            headers={"Content-Type": "application/json", **(
                {"Authorization": f"Bearer {token}"} if token else {})},
            method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return _json.load(r)

    admin = post("/api/v1/auth/login",
                 {"username": "admin", "password": "R6TestAdminPass!",
                  "role": "admin"})
    admin_tok = admin["token"]
    # Student row directly in the disposable test DB (no UI enroll needed).
    import psycopg
    from conftest import TEST_PG_DSN
    with psycopg.connect(TEST_PG_DSN) as conn:
        conn.execute(
            "INSERT INTO students (student_id, name, branch, embeddings) "
            "VALUES ('R6STU01', 'R6 Stu', 'CSE', '[]') "
            "ON CONFLICT (student_id) DO NOTHING")
        conn.commit()
    req = urllib.request.Request(
        api + "/api/v1/auth/provision-student",
        data=_json.dumps({"student_id": "R6STU01",
                          "password": "R6StudentPass!"}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {admin_tok}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200

    page.goto("http://r6-web")
    page.get_by_role("button", name="Student", exact=True).click()
    page.get_by_label("Username").fill("R6STU01")
    page.get_by_label("Password", exact=True).fill("R6StudentPass!")
    page.get_by_role("button", name="Login as").click()
    page.get_by_text("R6 Stu").first.wait_for(timeout=15000)
    assert stored_session(page)["role"] == "Student"
