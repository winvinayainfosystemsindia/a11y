"""Unit tests for the pure-Python parts of app.ai.tools.keyboard_nav_tool.
check_tab_order itself needs a live Playwright page, so it isn't unit-tested
here - only its stateless helpers."""
from app.ai.tools.keyboard_nav_tool import SUSPICIOUSLY_LOW_STOP_COUNT, _same_stop


def _stop(tag="button", selector=".x", x=10, y=20):
    return {"tag": tag, "selector": selector, "label": "", "x": x, "y": y, "visible": True}


def test_same_stop_true_when_tag_selector_and_position_match():
    a = _stop()
    b = _stop()
    assert _same_stop(a, b) is True


def test_same_stop_false_when_position_differs():
    a = _stop(x=10, y=20)
    b = _stop(x=10, y=99)
    assert _same_stop(a, b) is False


def test_same_stop_false_when_selector_differs():
    a = _stop(selector=".a")
    b = _stop(selector=".b")
    assert _same_stop(a, b) is False


def test_suspiciously_low_stop_count_is_a_small_positive_threshold():
    assert 0 < SUSPICIOUSLY_LOW_STOP_COUNT < 10
