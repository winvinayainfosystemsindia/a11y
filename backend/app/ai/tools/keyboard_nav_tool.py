"""
Simulates keyboard tab order / focus traversal (WCAG 2.4.3, 2.1.1, 2.4.7).
Presses Tab repeatedly on the live page and records what gets focus, then
flags focus traps and stops whose position suggests the tab order doesn't
follow visual/reading order.
"""
from __future__ import annotations

from playwright.async_api import Page

from app.config import settings

# A later tab stop landing this many px above the previous one is treated as
# a likely reading-order mismatch rather than incidental layout noise.
UPWARD_JUMP_THRESHOLD_PX = 40

# Below this many stops, an early "focus left the page" termination (rather
# than hitting max_stops) is more likely a cookie-banner/animation/overlay
# still settling and intercepting focus than a real page with almost no
# focusable elements - flag it instead of reporting a confident finding.
SUSPICIOUSLY_LOW_STOP_COUNT = 3

_FOCUS_PROBE_JS = """() => {
    const el = document.activeElement;
    if (!el || el === document.body) return null;
    const rect = el.getBoundingClientRect();
    const label = el.getAttribute('aria-label') || el.innerText || el.value || '';
    return {
        tag: el.tagName.toLowerCase(),
        selector: el.id ? ('#' + el.id) : (el.className && typeof el.className === 'string' ? ('.' + el.className.trim().split(/\\s+/)[0]) : el.tagName.toLowerCase()),
        label: String(label).trim().slice(0, 80),
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        visible: rect.width > 0 && rect.height > 0,
        html: (el.outerHTML || '').slice(0, 200),
    };
}"""


async def check_tab_order(page: Page, *, max_stops: int | None = None) -> dict:
    max_stops = max_stops or settings.AI_KEYBOARD_MAX_TAB_STOPS

    # The page may still be settling (cookie-consent banners, carousels,
    # lazy-mounted menus) when this tool runs - probing focus mid-mount is
    # what produced wildly different stop counts (e.g. 1 vs 29 vs 33) across
    # runs of the identical page. Give in-flight JS a chance to finish before
    # the first Tab press.
    try:
        await page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        pass  # busy-polling pages never go idle - fall through to the fixed settle wait below
    await page.wait_for_timeout(300)

    await page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")

    stops: list[dict] = []
    trap_detected = False
    ended_early = False

    for _ in range(max_stops):
        await page.keyboard.press("Tab")
        # Let synchronous focus-handling JS (a modal trapping focus on
        # mount, a menu expanding) settle before reading activeElement, so
        # the probe reflects the post-interaction DOM, not a mid-transition one.
        await page.wait_for_timeout(50)
        info = await page.evaluate(_FOCUS_PROBE_JS)
        if info is None:
            ended_early = True
            break
        if stops and _same_stop(stops[-1], info):
            trap_detected = True
            break
        stops.append(info)

    reordering_flags = []
    for previous, current in zip(stops, stops[1:]):
        if current["y"] < previous["y"] - UPWARD_JUMP_THRESHOLD_PX:
            reordering_flags.append(
                {
                    "from": previous,
                    "to": current,
                    "note": "Tab order jumps upward on the page - may not match visual/reading order",
                }
            )

    invisible_focus_targets = [stop for stop in stops if not stop["visible"]]

    # Focus returning to <body> (activeElement null) after only a couple of
    # stops is ambiguous: it could genuinely be a near-empty page, or it
    # could be an overlay/animation that grabbed and then released focus.
    # Surface that ambiguity explicitly instead of reporting it as an
    # equally-confident result as a full, uninterrupted traversal.
    possible_interference = ended_early and not trap_detected and len(stops) < SUSPICIOUSLY_LOW_STOP_COUNT

    return {
        "stops": stops,
        "stop_count": len(stops),
        "trap_detected": trap_detected,
        "reordering_flags": reordering_flags,
        "invisible_focus_targets": invisible_focus_targets,
        "possible_interference": possible_interference,
    }


def _same_stop(a: dict, b: dict) -> bool:
    return a["tag"] == b["tag"] and a["selector"] == b["selector"] and a["x"] == b["x"] and a["y"] == b["y"]
