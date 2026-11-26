"""R6-E settings: all MARP states, chaos confirmations, inject payloads."""
import json

from conftest import json_ok, login_as, stub_app_shell


def _settings(page, phase="ready", model_ready=True, db_connected=True,
              stage="READY", marp_state="READY"):
    stub_app_shell(page)
    status = {"phase": phase, "marp_state": marp_state, "stage": stage,
              "model_ready": model_ready, "db_connected": db_connected,
              "uptime_s": 42.0, "active_session": {}, "chaos": {},
              "metrics": {}}
    page.unroute("**/api/v1/marp/status")
    page.route("**/api/v1/marp/status",
               lambda r: r.fulfill(**json_ok(status)))
    login_as(page, role="admin", token="mock-set-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    page.get_by_role("navigation").get_by_role("button", name="Settings").click()
    page.get_by_text("Settings & MARP chaos hub").wait_for(timeout=5000)


def test_each_marx_state_maps_to_expected_label(page):
    cases = [
        ({"phase": "loading_model_weights", "model_ready": False,
          "marp_state": "LOADING_WEIGHTS"}, "Loading"),
        ({"phase": "timeout: detector load exceeded budget",
          "model_ready": False, "marp_state": "FAILED_TIMEOUT"},
         "Load timeout"),
        ({"phase": "db_failed: conn refused", "model_ready": False,
          "marp_state": "FAILED_DB"}, "Database failure"),
        ({"phase": "detector_failed: boom", "model_ready": False,
          "marp_state": "FAILED_MODEL"}, "Model failure"),
        ({"phase": "detector_busy: previous load still active",
          "model_ready": False, "marp_state": "FAILED_BUSY"},
         "Detector busy"),
        ({"phase": "chaos: probe refusal (in-situ)", "model_ready": False,
          "marp_state": "FAILED_PROBE"}, "Chaos injected"),
        ({"phase": "ready", "model_ready": True, "db_connected": True,
          "marp_state": "READY"}, "Ready"),
        ({"phase": "ready", "model_ready": True, "db_connected": False,
          "marp_state": "READY"}, "Database down"),
    ]
    for kwargs, label in cases:
        _settings(page, **kwargs)
        # The panel reflects the 2s status poll; wait like a user would.
        page.get_by_text(label, exact=True).wait_for(timeout=8000)


def test_destructive_controls_require_confirmation(page):
    _settings(page)
    posted = []
    page.route("**/api/chaos/db-drop",
               lambda r: (posted.append(r.request.method),
                          r.fulfill(**json_ok({"ok": True})))[1])
    page.get_by_role("button", name="DB drop").click()
    page.get_by_role("dialog").wait_for(timeout=5000)
    page.get_by_role("button", name="Cancel").click()
    assert posted == [], "cancelled chaos must not POST"
    assert page.get_by_text("Settings & MARP chaos hub").is_visible()
    page.get_by_role("button", name="DB drop").click()
    page.get_by_role("button", name="Confirm", exact=True).click()
    page.wait_for_timeout(1000)
    assert posted == ["POST"], posted


def test_recover_posts_without_modal_but_with_auth(page):
    _settings(page)
    seen = {}
    page.route("**/api/chaos/recover",
               lambda r: (seen.update(auth=r.request.headers.get(
                   "authorization")), r.fulfill(**json_ok({"ok": True})))[1])
    page.get_by_role("button", name="Recover").click()
    page.wait_for_timeout(1000)
    assert seen.get("auth") == "Bearer mock-set-1", seen


def test_apply_chaos_sends_configured_payload(page):
    _settings(page)
    bodies = []
    def _capture(r):
        import json as _json
        bodies.append(_json.loads(r.request.post_data or "{}"))
        r.fulfill(**json_ok({"ok": True, "chaos": {}}))

    page.route("**/api/v1/marp/chaos/inject", _capture)
    page.get_by_role("button", name="Probe refusal").click()
    assert "Probe refusal on" in page.content()
    page.get_by_role("button", name="Apply chaos injection").click()
    page.wait_for_timeout(1000)
    assert bodies, "inject must POST"
    assert bodies[0]["artificial_probe_failure"] is True
    assert bodies[0]["simulated_latency_sec"] == 0
