"""Unit tests for the pure-Python parts of app.ai.tools.contrast_tool -
color parsing and ratio math. The embedded JS (effective background-color
compositing) is validated separately via Node since this project has no
browser test harness; see the regression note in contrast_tool.py."""
from app.ai.tools.contrast_tool import (
    contrast_ratio,
    evaluate_contrast,
    is_large_text,
    parse_color,
    required_ratio,
)


def test_parse_color_hex_6_digit():
    assert parse_color("#767676") == (0x76, 0x76, 0x76)


def test_parse_color_hex_3_digit():
    assert parse_color("#fff") == (255, 255, 255)


def test_parse_color_rgb():
    assert parse_color("rgb(119, 119, 119)") == (119, 119, 119)


def test_parse_color_rgba_ignores_alpha_for_the_rgb_triplet():
    """parse_color itself only extracts r/g/b - alpha handling (treating a
    near-zero alpha as 'no real color here') now happens in the JS effective-
    background-color resolution *before* this function ever sees the value,
    not here. This test just documents that parse_color's own contract is
    unchanged: give it an already-resolved opaque color string."""
    assert parse_color("rgba(0, 0, 0, 0.5)") == (0, 0, 0)


def test_parse_color_invalid_returns_none():
    assert parse_color("currentColor") is None
    assert parse_color("") is None


def test_contrast_ratio_black_on_white_is_max():
    assert contrast_ratio("rgb(0,0,0)", "rgb(255,255,255)") == 21.0


def test_contrast_ratio_identical_colors_is_one():
    assert contrast_ratio("rgb(50,50,50)", "rgb(50,50,50)") == 1.0


def test_contrast_ratio_none_when_unparseable():
    assert contrast_ratio("garbage", "rgb(255,255,255)") is None


def test_required_ratio_aa_vs_aaa():
    assert required_ratio(is_large=False, level="AA") == 4.5
    assert required_ratio(is_large=True, level="AA") == 3.0
    assert required_ratio(is_large=False, level="AAA") == 7.0
    assert required_ratio(is_large=True, level="AAA") == 4.5


def test_is_large_text_thresholds():
    assert is_large_text(24.0, 400) is True
    assert is_large_text(23.9, 400) is False
    assert is_large_text(18.66, 700) is True
    assert is_large_text(18.0, 700) is False


def test_evaluate_contrast_reports_measured_and_required():
    result = evaluate_contrast(
        foreground="rgb(119, 119, 119)", background="rgb(255, 255, 255)",
        font_size_px=16, font_weight=400, level="AA",
    )
    assert result["ratio"] == contrast_ratio("rgb(119, 119, 119)", "rgb(255, 255, 255)")
    assert result["required_ratio"] == 4.5
    assert result["is_large_text"] is False
    assert result["foreground"] == "rgb(119, 119, 119)"
    assert result["background"] == "rgb(255, 255, 255)"
