"""R6-B dashboards, navigation, empty/loading/error states."""
from conftest import login_as, stub_app_shell


def _hub(page, sessions, **kw):
    stub_app_shell(page, sessions=sessions, **kw)
    login_as(page, role="admin", token="mock-dash-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)


def test_dashboard_renders_real_supplied_data(page):
    sessions = [
        {"session_id": 7, "session_name": "Morning", "date": "2026-01-01",
         "total": 4, "present": 3, "absent": 1},
        {"session_id": 8, "session_name": "Lab", "date": "2026-01-02",
         "total": 4, "present": 1, "absent": 3},
    ]
    _hub(page, sessions,
         students=[{"student_id": "S1", "name": "A", "branch": "CSE"}])
    assert page.get_by_text("Total students", exact=True).is_visible()
    assert page.get_by_text("2", exact=True).first.is_visible()
    assert page.get_by_text("#7 Morning").is_visible()
    assert page.get_by_text("Session log", exact=True).is_visible()


def test_navigation_selects_screen_and_marks_active(page):
    _hub(page, [])
    page.get_by_role("navigation").get_by_role("button", name="Attendance").click()
    assert page.get_by_text("Live camera view").is_visible()
    assert page.get_by_role("button", name="Attendance").get_attribute(
        "aria-pressed") == "true"
    page.get_by_role("navigation").get_by_role("button", name="Students").click()
    assert page.get_by_text("Student profile").is_visible()
    page.get_by_role("navigation").get_by_role("button", name="Settings").click()
    assert page.get_by_text("Settings & MARP chaos hub").is_visible()
    page.get_by_role("navigation").get_by_role("button", name="Dashboard").click()
    assert page.get_by_text("Session log").is_visible()


def test_empty_states_are_honest(page):
    _hub(page, [])
    assert page.get_by_text("No sessions yet").count() >= 1
    assert page.get_by_text("No sessions match this filter.").is_visible()


def test_filter_changes_visible_rows(page):
    sessions = [
        {"session_id": 1, "session_name": "A", "date": "2026-01-01",
         "total": 4, "present": 4, "absent": 0},
        {"session_id": 2, "session_name": "B", "date": "2026-01-02",
         "total": 4, "present": 0, "absent": 4},
    ]
    _hub(page, sessions)
    assert page.get_by_text("#1 A").is_visible()
    page.get_by_label("Filter sessions").select_option("Logs (Absent-heavy)")
    assert page.get_by_text("#2 B").is_visible()
    assert page.get_by_text("#1 A").count() == 0


def test_status_indicator_is_not_color_only(page):
    _hub(page, [])
    # Status arrives via the 2s telemetry poll; wait for it like a user would.
    page.get_by_text("Online", exact=True).wait_for(timeout=8000)
    page.get_by_role("navigation").get_by_role("button", name="Settings").click()
    assert page.get_by_text("Ready", exact=True).is_visible()
