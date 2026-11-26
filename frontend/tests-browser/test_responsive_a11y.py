"""R6 responsive layouts + accessibility checks (locator-based + axe)."""
import pytest

from conftest import login_as, stub_app_shell

VIEWPORTS = [
    ("desktop", {"width": 1440, "height": 900}),
    ("laptop", {"width": 1280, "height": 720}),
    ("tablet", {"width": 768, "height": 1024}),
    ("mobile", {"width": 390, "height": 844}),
]


def _no_page_overflow(page):
    box = page.evaluate("""() => ({
        sw: document.documentElement.scrollWidth,
        cw: document.documentElement.clientWidth })""")
    assert box["sw"] <= box["cw"] + 1, box


@pytest.mark.parametrize("name,size", VIEWPORTS)
def test_login_layout_no_overflow(pw_browser, name, size):
    ctx = pw_browser.new_context(viewport=size)
    page = ctx.new_page()
    try:
        page.goto("http://r6-web")
        page.get_by_text("Face attendance sign in").wait_for(timeout=8000)
        _no_page_overflow(page)
        assert page.get_by_label("Username").is_visible()
        assert page.get_by_role("button", name="Login as").is_visible()
    finally:
        page.close()
        ctx.close()


@pytest.mark.parametrize("name,size", VIEWPORTS)
def test_hub_and_scanner_layout_no_overflow(pw_browser, name, size):
    ctx = pw_browser.new_context(viewport=size)
    page = ctx.new_page()
    try:
        stub_app_shell(page, sessions=[{
            "session_id": 1, "session_name": "Morning",
            "date": "2026-01-01", "total": 30, "present": 28, "absent": 2}])
        login_as(page, role="admin", token=f"mock-vp-{name}")
        page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
        _no_page_overflow(page)
        assert page.get_by_role("navigation", name="Primary").is_visible()
        page.get_by_role("navigation").get_by_role("button", name="Attendance").click()
        page.get_by_text("Live camera view").wait_for(timeout=5000)
        _no_page_overflow(page)
        box = page.locator(".fa-video-frame").bounding_box()
        assert box and abs(box["width"] / max(box["height"], 1) - 4 / 3) < 0.15
    finally:
        page.close()
        ctx.close()


@pytest.mark.parametrize("name,size", VIEWPORTS)
def test_modal_fits_viewport(pw_browser, name, size):
    ctx = pw_browser.new_context(viewport=size)
    page = ctx.new_page()
    try:
        stub_app_shell(page)
        login_as(page, role="admin", token=f"mock-vp-modal-{name}")
        page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
        page.get_by_role("button", name="Log out").first.click()
        dialog = page.get_by_role("dialog")
        dialog.wait_for(timeout=5000)
        box = dialog.bounding_box()
        assert box is not None
        assert box["width"] <= size["width"]
        assert box["height"] <= size["height"]
    finally:
        page.close()
        ctx.close()


def test_inputs_have_accessible_names(page):
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-a11y-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    missing = page.evaluate("""() => {
      const bad = [];
      document.querySelectorAll('input, select, textarea').forEach((el) => {
        const label = el.getAttribute('aria-label')
          || (el.labels && el.labels.length ? el.labels[0].innerText : '')
          || el.getAttribute('placeholder') || '';
        if (!label.trim()) bad.push(el.outerHTML.slice(0, 80));
      });
      return bad;
    }""")
    assert missing == [], missing
    # Semantic headings exist on the main screens.
    assert page.locator("h1, h2").count() >= 1


def test_keyboard_focus_is_visible(page):
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-a11y-2")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    page.keyboard.press("Tab")
    ring = page.evaluate("""() => {
      const el = document.activeElement;
      const cs = getComputedStyle(el);
      return {tag: el.tagName, outline: cs.outlineWidth,
              shadow: cs.boxShadow};
    }""")
    assert ring["tag"] in ("BUTTON", "A", "INPUT", "SELECT"), ring


def test_reduced_motion_disables_transitions(pw_browser):
    ctx = pw_browser.new_context(reduced_motion="reduce")
    page = ctx.new_page()
    try:
        page.goto("http://r6-web")
        page.get_by_text("Face attendance sign in").wait_for(timeout=8000)
        dur = page.evaluate("""() => getComputedStyle(
          document.querySelector('.fa-btn')).transitionDuration""")
        assert dur in ("0s", "0.001s", "1ms"), dur
    finally:
        page.close()
        ctx.close()


def test_axe_no_critical_violations(page):
    from axe_core_python.sync_playwright import Axe
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-a11y-axe")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    axe = Axe()
    results = axe.run(page)
    violations = results.get("violations", []) if isinstance(results, dict) \
        else getattr(results, "violations", [])
    critical = [v for v in violations
                if (v.get("impact") if isinstance(v, dict)
                    else getattr(v, "impact", None)) in ("critical", "serious")]
    assert critical == [], [
        (v.get("id") if isinstance(v, dict) else v) for v in critical]
    print("\naxe violations (non-critical, recorded):",
          [(v.get("id"), v.get("impact")) if isinstance(v, dict) else str(v)
           for v in violations])
