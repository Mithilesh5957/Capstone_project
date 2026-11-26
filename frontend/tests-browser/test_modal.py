"""R6 modal: focus trap, Escape, backdrop, focus restore, scroll lock."""
from conftest import login_as, stored_session, stub_app_shell


def _open_logout(page):
    stub_app_shell(page)
    login_as(page, role="admin", token="mock-modal-1")
    page.get_by_text("Dashboard", exact=True).wait_for(timeout=8000)
    page.get_by_role("button", name="Log out").first.click()
    page.get_by_role("dialog").wait_for(timeout=5000)


def _active_label(page):
    # innerText reflects CSS text-transform (buttons render uppercase);
    # normalize for comparison while asserting the real focused element.
    return page.evaluate(
        "() => { const el = document.activeElement; "
        "const t = el ? (el.innerText || el.getAttribute('aria-label') || el.tagName) : 'none'; "
        "return t.toLowerCase(); }")


def test_focus_moves_into_dialog_on_open(page):
    _open_logout(page)
    assert "stay signed in" in _active_label(page)


def test_tab_cycles_inside_dialog(page):
    _open_logout(page)
    labels = set()
    for _ in range(6):
        page.keyboard.press("Tab")
        labels.add(_active_label(page).strip())
    assert labels <= {"stay signed in", "log out"}, labels
    assert len(labels) == 2


def test_shift_tab_wraps_backward(page):
    _open_logout(page)
    # First control has initial focus; Shift+Tab must wrap to the last one.
    assert "stay signed in" in _active_label(page)
    page.keyboard.press("Shift+Tab")
    assert "log out" in _active_label(page)


def test_escape_closes_and_restores_focus(page):
    _open_logout(page)
    page.keyboard.press("Escape")
    page.get_by_role("dialog").wait_for(state="detached", timeout=5000)
    assert "log out" in _active_label(page)
    assert stored_session(page) is not None


def test_backdrop_click_cancels_but_interior_does_not(page):
    _open_logout(page)
    page.get_by_text("Log out?", exact=True).click()
    assert page.get_by_role("dialog").count() == 1
    page.mouse.click(8, 8)  # backdrop corner, outside the 440px dialog
    page.get_by_role("dialog").wait_for(state="detached", timeout=5000)


def test_scroll_locked_while_open_and_restored(page):
    _open_logout(page)
    assert page.evaluate("() => getComputedStyle(document.body).overflow") == "hidden"
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    assert page.evaluate("() => getComputedStyle(document.body).overflow") != "hidden"


def test_repeated_open_close_keeps_working(page):
    _open_logout(page)
    for _ in range(3):
        page.keyboard.press("Escape")
        page.get_by_role("dialog").wait_for(state="detached", timeout=5000)
        page.get_by_role("button", name="Log out").first.click()
        page.get_by_role("dialog").wait_for(timeout=5000)
    page.get_by_role("button", name="Log out", exact=True).last.click()
    page.get_by_text("Face attendance sign in").wait_for(timeout=5000)
    assert stored_session(page) is None


def test_confirm_performs_logout_only_when_confirmed(page):
    _open_logout(page)
    # Clicking the dialog title must not dismiss or confirm anything.
    page.get_by_text("Log out?", exact=True).click()
    assert page.get_by_role("dialog").count() == 1
    assert stored_session(page) is not None
    page.get_by_role("button", name="Log out", exact=True).last.click()
    page.get_by_text("Face attendance sign in").wait_for(timeout=5000)
