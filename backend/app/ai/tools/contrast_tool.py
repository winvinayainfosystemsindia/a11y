"""
Color contrast ratio calculation (WCAG 1.4.3 / 1.4.6). Pure math on parsed
colors, plus an optional live re-measurement of a specific selector via the
already-open Playwright page.
"""
from __future__ import annotations

import re

from playwright.async_api import Page

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*[\d.]+\s*)?\)")

# Large text: >= 18pt (24px) regular, or >= 14pt (18.66px) bold.
LARGE_TEXT_PX = 24.0
LARGE_TEXT_BOLD_PX = 18.66
BOLD_WEIGHT_THRESHOLD = 700


def parse_color(value: str) -> tuple[int, int, int] | None:
    value = (value or "").strip()
    hex_match = _HEX_RE.match(value)
    if hex_match:
        hex_value = hex_match.group(1)
        if len(hex_value) == 3:
            hex_value = "".join(ch * 2 for ch in hex_value)
        return tuple(int(hex_value[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

    rgb_match = _RGB_RE.match(value)
    if rgb_match:
        return tuple(round(float(component)) for component in rgb_match.groups())  # type: ignore[return-value]

    return None


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        c_srgb = c / 255.0
        return c_srgb / 12.92 if c_srgb <= 0.03928 else ((c_srgb + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: str, bg: str) -> float | None:
    fg_rgb = parse_color(fg)
    bg_rgb = parse_color(bg)
    if fg_rgb is None or bg_rgb is None:
        return None
    l1 = _relative_luminance(fg_rgb) + 0.05
    l2 = _relative_luminance(bg_rgb) + 0.05
    return round(max(l1, l2) / min(l1, l2), 2)


def is_large_text(font_size_px: float, font_weight: int) -> bool:
    if font_weight >= BOLD_WEIGHT_THRESHOLD:
        return font_size_px >= LARGE_TEXT_BOLD_PX
    return font_size_px >= LARGE_TEXT_PX


def required_ratio(*, is_large: bool, level: str) -> float:
    if level == "AAA":
        return 4.5 if is_large else 7.0
    return 3.0 if is_large else 4.5


def evaluate_contrast(
    *, foreground: str, background: str, font_size_px: float, font_weight: int, level: str = "AA"
) -> dict:
    ratio = contrast_ratio(foreground, background)
    large = is_large_text(font_size_px, font_weight)
    threshold = required_ratio(is_large=large, level=level)
    return {
        "ratio": ratio,
        "required_ratio": threshold,
        "is_large_text": large,
        "passes": ratio is not None and ratio >= threshold,
        "foreground": foreground,
        "background": background,
    }


# getComputedStyle(el).backgroundColor is almost always "rgba(0, 0, 0, 0)"
# (fully transparent) for ordinary text elements - the actual painted
# background lives on an ancestor. Reading that raw value directly parses to
# opaque black (see parse_color), which is indistinguishable from a real
# black background and was producing bogus ratio=1.0 "black on black"
# findings for perfectly normal text. This walks up the DOM alpha-compositing
# each ancestor's background until fully opaque (or falls back to the
# browser's white canvas), mirroring what a user actually sees. Nested
# *inside* each evaluate()'d function body (rather than injected as a
# sibling top-level declaration) since Playwright's page.evaluate() expects
# exactly one function expression per call.
_EFFECTIVE_BG_HELPER_JS = """
        function getEffectiveBackgroundColor(el) {
            function parseRGBA(str) {
                const m = /rgba?\\(([\\d.]+),\\s*([\\d.]+),\\s*([\\d.]+)(?:,\\s*([\\d.]+))?\\)/.exec(str || '');
                if (!m) return null;
                return { r: parseFloat(m[1]), g: parseFloat(m[2]), b: parseFloat(m[3]), a: m[4] === undefined ? 1 : parseFloat(m[4]) };
            }
            let acc = { r: 0, g: 0, b: 0, a: 0 };
            let node = el;
            while (node && acc.a < 1) {
                const bg = parseRGBA(getComputedStyle(node).backgroundColor);
                if (bg && bg.a > 0) {
                    const outA = acc.a + bg.a * (1 - acc.a);
                    if (outA > 0) {
                        acc = {
                            r: (acc.r * acc.a + bg.r * bg.a * (1 - acc.a)) / outA,
                            g: (acc.g * acc.a + bg.g * bg.a * (1 - acc.a)) / outA,
                            b: (acc.b * acc.a + bg.b * bg.a * (1 - acc.a)) / outA,
                            a: outA,
                        };
                    }
                }
                node = node.parentElement;
            }
            const r = Math.round(acc.r * acc.a + 255 * (1 - acc.a));
            const g = Math.round(acc.g * acc.a + 255 * (1 - acc.a));
            const b = Math.round(acc.b * acc.a + 255 * (1 - acc.a));
            return 'rgb(' + r + ', ' + g + ', ' + b + ')';
        }
"""


async def check_selector_contrast(page: Page, selector: str, *, level: str = "AA") -> dict | None:
    """Live re-measurement of one selector's computed styles - used when a
    planner step targets a specific element rather than relying on the
    contrast samples already gathered during PERCEIVE."""
    info = await page.evaluate(
        """(sel) => {"""
        + _EFFECTIVE_BG_HELPER_JS
        + """
            const el = document.querySelector(sel);
            if (!el) return null;
            const style = getComputedStyle(el);
            return {
                color: style.color,
                backgroundColor: getEffectiveBackgroundColor(el),
                fontSize: parseFloat(style.fontSize),
                fontWeight: parseInt(style.fontWeight, 10) || 400,
                html: (el.outerHTML || '').slice(0, 200),
            };
        }""",
        selector,
    )
    if info is None:
        return None
    result = evaluate_contrast(
        foreground=info["color"],
        background=info["backgroundColor"],
        font_size_px=info["fontSize"],
        font_weight=info["fontWeight"],
        level=level,
    )
    result["html"] = info["html"]
    return result
