"""R6 CSV: client export vs source data, escaping, empty/failed cases."""
import csv
import io

from conftest import login_as, stub_app_shell


def _hub_with_sessions(page, sessions):
    stub_app_shell(page, sessions=sessions)
    login_as(page, role="admin", token="mock-csv-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)


def test_export_matches_source_data_with_escaping(page, tmp_path):
    sessions = [{
        "session_id": 7,
        "session_name": 'Morning, "Special"\nSession',
        "date": "2026-01-01", "total": 2, "present": 1, "absent": 1}]
    _hub_with_sessions(page, sessions)
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export sessions").click()
    download = dl.value
    assert download.suggested_filename == "faceattend_sessions.csv"
    path = tmp_path / "out.csv"
    download.save_as(path)
    rows = list(csv.DictReader(io.StringIO(
        path.read_text(encoding="utf-8"))))
    assert len(rows) == 1
    assert rows[0]["session_id"] == "7"
    assert rows[0]["session_name"] == 'Morning, "Special"\nSession'
    assert rows[0]["date"] == "2026-01-01"
    assert rows[0]["total"] == "2"
    assert rows[0]["present"] == "1"
    assert rows[0]["absent"] == "1"


def test_failed_fetch_produces_no_fabricated_export(page, tmp_path):
    stub_app_shell(page, sessions=[])
    # Registered after the default stub, so it wins: fetch fails.
    page.route("**/api/attendance/sessions*",
               lambda r: r.abort())
    login_as(page, role="admin", token="mock-csv-2")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    assert page.get_by_text("No sessions yet").count() >= 1
    # Export of an empty list is header-only: truthful, no invented rows.
    with page.expect_download() as dl:
        page.get_by_role("button", name="Export sessions").click()
    path = tmp_path / "empty.csv"
    dl.value.save_as(path)
    text = path.read_text(encoding="utf-8").strip()
    assert text == "session_id,session_name,date,total,present,absent"
