"""
Export helpers for the final audit report.

Two formats are supported:
  - Excel (.xlsx): a single workbook with two worksheets -- "Defects" and
    "Test Cases" -- both populated from the results dict produced by
    audit_controller.get_results().
  - Word (.docx): the firm's own Accessibility Conformance Certificate
    template (see app/utils/conformance_report.py), filled with this run's
    real per-criterion results.

Neither function touches the database; they receive the plain dict that
get_results() already builds, so the route layer just pipes the output
straight to a StreamingResponse.
"""
from __future__ import annotations

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment,
    Border,
    Font,
    PatternFill,
    Side,
)
from openpyxl.utils import get_column_letter

from app.utils import conformance_report
from app.utils.wcag_criteria import all_success_criteria, principle_for_criterion

# -- Palette ------------------------------------------------------------------
_HEADER_BG = "1E3A5F"          # deep navy
_HEADER_FG = "FFFFFF"          # white
_DEFECT_HEADER_BG = "8B1A1A"   # deep red  (Defects sheet)
_ALT_ROW_BG = "EFF3F8"         # very light blue
_PASS_BG = "D6F0DA"            # light green
_FAIL_BG = "FAD7D7"            # light red
_REVIEW_BG = "FFF3CD"          # light amber

_SEVERITY_BG = {
    "Critical": "FF4444",
    "High":     "FF8800",
    "Medium":   "FFD700",
    "Low":      "90EE90",
    # "Review Needed" is a confidence state, not a real severity ranking -
    # give it its own (amber, matching _REVIEW_BG) color so it never visually
    # blends into a default/unstyled row next to genuinely-ranked severities.
    "Review Needed": _REVIEW_BG,
}

_STATUS_BG = {
    "pass":         _PASS_BG,
    "fail":         _FAIL_BG,
    "needs_review": _REVIEW_BG,
}

_VERIFICATION_STATUS_BG = {
    # No highlight for "Confirmed" - it's the normal/definitive case. Amber
    # flags the rows that still need a human look before being trusted.
    "AI Judgment - Needs Review": _REVIEW_BG,
}

_DEFECT_STATUS_BG = {
    "Open":         _FAIL_BG,
    "In Progress":  _REVIEW_BG,
    "Retest":       _REVIEW_BG,
    "Fixed":        _PASS_BG,
    "Closed":       _PASS_BG,
    "Won't Fix":    _ALT_ROW_BG,
}

_THIN = Side(border_style="thin", color="CCCCCC")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


# ─── Excel helpers ────────────────────────────────────────────────────────────

def _xl_header_row(ws, columns: list[str], bg_hex: str) -> None:
    """Write a styled header row to the worksheet."""
    fill = PatternFill("solid", fgColor=bg_hex)
    font = Font(bold=True, color=_HEADER_FG, size=10)
    for col_idx, title in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=title)
        cell.fill = fill
        cell.font = font
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _xl_data_cell(cell, value: Any, bg_hex: str | None = None, *, wrap: bool = True) -> None:
    cell.value = value if value is not None else ""
    cell.border = _BORDER
    cell.alignment = Alignment(vertical="top", wrap_text=wrap)
    if bg_hex:
        cell.fill = PatternFill("solid", fgColor=bg_hex)


def _xl_autowidth(ws, columns: list[str], max_width: int = 60) -> None:
    """Set reasonable column widths (capped). Long-text columns get 55."""
    _WIDE_HEADERS = {
        "Expected Result\n(Screen Reader User Perspective)",
        "Actual Result\n(Screen Reader User Perspective)",
        "Steps to Reproduce", "Description",
        "Suggestion to Fix", "Remediation",
        "Test Case Name", "HTML Snippet",
        "Description / Requirement", "Success Criterion Name",
    }
    for col_idx, header in enumerate(columns, start=1):
        col_letter = get_column_letter(col_idx)
        if header in _WIDE_HEADERS:
            ws.column_dimensions[col_letter].width = 55
        else:
            ws.column_dimensions[col_letter].width = min(max(len(header) + 4, 12), max_width)


def _write_defects_sheet(ws, defects: list[dict]) -> None:
    columns = [
        "Defect ID", "Test Case ID", "Page Title", "Page URL",
        "Principle", "Criteria", "Level", "Element / Component Type on Page",
        "Severity", "Status", "Verification Status", "Confidence", "Defect Status",
        "Description",
        "Expected Result\n(Screen Reader User Perspective)",
        "Actual Result\n(Screen Reader User Perspective)",
        "Steps to Reproduce", "Suggestion to Fix", "HTML Snippet",
    ]
    keys = [
        "defect_id", "test_case_id", "page_title", "page_url",
        "principle", "criteria", "level", "element_type",
        "severity", "status", "verification_status", "confidence", "defect_status",
        "description", "expected_result", "actual_result",
        "steps_to_reproduce", "suggestion_to_fix", "html_snippet",
    ]

    _xl_header_row(ws, columns, _DEFECT_HEADER_BG)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 40

    for row_idx, defect in enumerate(defects, start=2):
        bg = _ALT_ROW_BG if row_idx % 2 == 0 else None
        for col_idx, key in enumerate(keys, start=1):
            value = defect.get(key)
            if key == "confidence":
                value = f"{value:.0%}" if isinstance(value, (int, float)) else value
                cell_bg = bg
            elif key == "status":
                cell_bg = _STATUS_BG.get(value or "", bg)
            elif key == "verification_status":
                cell_bg = _VERIFICATION_STATUS_BG.get(value or "", bg)
            elif key == "defect_status":
                cell_bg = _DEFECT_STATUS_BG.get(value or "", bg)
            elif key == "severity":
                cell_bg = _SEVERITY_BG.get(value or "", bg)
            else:
                cell_bg = bg
            _xl_data_cell(ws.cell(row=row_idx, column=col_idx), value, cell_bg)
        ws.row_dimensions[row_idx].height = 80

    _xl_autowidth(ws, columns)


def _write_testcases_sheet(ws, test_cases: list[dict]) -> None:
    columns = [
        "Test Case ID", "Test Case Name", "Page Title", "Page URL",
        "Principle", "Criteria", "Level", "Element / Component Type on Page",
        "Severity", "Status",
        "Description",
        "Expected Result\n(Screen Reader User Perspective)",
        "Actual Result\n(Screen Reader User Perspective)",
        "Steps to Reproduce", "Remediation",
    ]
    keys = [
        "test_case_id", "tc_name", "page_title", "page_url",
        "principle", "criteria", "level", "element_type",
        "severity", "status",
        "description", "expected_result", "actual_result",
        "steps_to_reproduce", "remediation",
    ]

    _xl_header_row(ws, columns, _HEADER_BG)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 40

    for row_idx, tc in enumerate(test_cases, start=2):
        bg = _ALT_ROW_BG if row_idx % 2 == 0 else None
        for col_idx, key in enumerate(keys, start=1):
            value = tc.get(key)
            if key == "status":
                cell_bg = _STATUS_BG.get(value or "", bg)
            elif key == "severity":
                cell_bg = _SEVERITY_BG.get(value or "", bg)
            else:
                cell_bg = bg
            _xl_data_cell(ws.cell(row=row_idx, column=col_idx), value, cell_bg)
        ws.row_dimensions[row_idx].height = 80

    _xl_autowidth(ws, columns)


def _write_success_criteria_sheet(ws) -> None:
    """The standalone WCAG Success Criteria Library reference sheet - static
    data, independent of any specific audit run's results."""
    columns = [
        "S.No", "SC Number", "Success Criterion Name", "WCAG Version",
        "Level", "Principle", "Guideline", "Description / Requirement",
    ]
    _xl_header_row(ws, columns, _HEADER_BG)
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 40

    for row_idx, criterion in enumerate(all_success_criteria(), start=2):
        bg = _ALT_ROW_BG if row_idx % 2 == 0 else None
        values = [
            row_idx - 1,
            criterion.sc_number,
            criterion.name,
            criterion.wcag_version,
            criterion.level,
            principle_for_criterion(criterion.sc_number),
            criterion.guideline,
            criterion.description,
        ]
        for col_idx, value in enumerate(values, start=1):
            _xl_data_cell(ws.cell(row=row_idx, column=col_idx), value, bg)
        ws.row_dimensions[row_idx].height = 60

    _xl_autowidth(ws, columns)


def build_excel_report(results: dict) -> bytes:
    """
    Build a three-sheet Excel workbook from a get_results() dict.

    Sheet 1 "Defects"           -- failed / needs_review items with full defect columns.
    Sheet 2 "Test Cases"        -- all items including passed ones.
    Sheet 3 "Success Criteria"  -- static reference: all 56 WCAG 2.0/2.1/2.2 A+AA criteria.
    """
    wb = Workbook()

    ws_defects = wb.active
    ws_defects.title = "Defects"
    _write_defects_sheet(ws_defects, results.get("defects", []))

    ws_tc = wb.create_sheet(title="Test Cases")
    _write_testcases_sheet(ws_tc, results.get("test_cases", []))

    ws_sc = wb.create_sheet(title="Success Criteria")
    _write_success_criteria_sheet(ws_sc)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ─── Word ─────────────────────────────────────────────────────────────────

def build_word_report(results: dict) -> bytes:
    """The "Download IAAP Word Report" button's output - the firm's own
    Accessibility Conformance Certificate template (app/utils/
    conformance_report.py), filled with this audit run's real results,
    rather than a generic from-scratch document."""
    return conformance_report.build_conformance_certificate(results)
