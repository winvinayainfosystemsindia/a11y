"""
Business logic for the AI audit agent: starting runs (single + batch),
polling status, and mapping a completed run's results onto the Test Case
sheet, the Defects report, and an IAAP-style audit report summary
(conformance broken down by WCAG principle/level/severity, paired with the
LLM-authored executive summary from REFLECT). Every count/tally here is
computed deterministically from stored StepResults - never asked of the
LLM - so the numbers in the report can't drift from what was actually found.

app/ai/agent.py is the ONLY module imported from app/ai/ here - this
controller never reaches into planner.py, executor.py, reflector.py, or
anything under app/ai/memory or app/ai/tools directly (spec requirement).
"""
from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

from sqlalchemy.orm import Session

from app.ai.agent import run_audit
from app.config import settings
from app.controllers.errors import DomainError, NotFoundError
from app.models.audit_execution import AuditExecution
from app.models.audit_run import AuditRun, TERMINAL_STATUSES
from app.models.plan_step import PlanStep
from app.models.project import Project
from app.repositories import audit_repository
from app.utils.wcag_criteria import axe_rules_for_criterion, criterion_name, principle_for_criterion

_SEVERITY_BY_AXE_IMPACT = {"critical": "Critical", "serious": "High", "moderate": "Medium", "minor": "Low"}
_AXE_IMPACT_ORDER = list(_SEVERITY_BY_AXE_IMPACT.keys())

_REMEDIATION_HINTS = {
    "1.1.1": 'Add meaningful alt text (or alt="" for purely decorative images) that conveys the same information '
    "or function as the image.",
    "1.3.1": "Associate labels/headers programmatically (semantic HTML or ARIA) so assistive technology exposes "
    "the same structure sighted users see.",
    "1.3.2": "Reorder the DOM (or adjust CSS-driven visual order) so the reading order presented to a screen "
    "reader matches the intended sequence.",
    "1.3.3": "Reword the instruction/content so it doesn't rely solely on shape, size, position, or color.",
    "1.4.1": "Ensure information conveyed by color is also conveyed through text, an icon, or another non-color cue.",
    "1.4.3": "Increase the contrast between text and background color to meet the required ratio for that text size.",
    "1.4.11": "Increase the contrast of non-text UI components (icons, borders, focus indicators) against adjacent colors.",
    "2.1.1": "Ensure all interactive functionality is operable via keyboard alone, with no mouse-only handlers.",
    "2.1.2": "Ensure keyboard focus can always move away from every component using standard navigation keys.",
    "2.4.1": "Add a working skip link and/or landmark regions so keyboard/screen reader users can bypass repeated blocks.",
    "2.4.3": "Reorder DOM elements (or apply tabindex carefully) so the tab order follows the visual/reading order.",
    "2.4.4": "Rewrite the link text so its purpose is clear without relying on surrounding context.",
    "2.4.6": "Give headings/labels text that describes the content or purpose that follows them.",
    "2.4.7": "Ensure every focusable element has a clearly visible focus indicator.",
    "3.3.1": "Identify the specific field(s) in error and describe the error in text, not color/icon alone.",
    "3.3.2": "Provide a visible label or instructions for every form field.",
    "3.3.3": "Suggest a specific correction alongside the error identification.",
    "4.1.2": "Ensure every UI component exposes an accessible name, role, and value via semantic HTML or ARIA.",
    "4.1.3": 'Announce dynamic content changes to assistive technology via aria-live, role="status"/"alert", or '
    "an equivalent mechanism, without forcing a focus change.",
}

_METHODOLOGY_TEMPLATE = (
    "Automated and AI-assisted accessibility audit against WCAG 2.1 Level {level}, covering all four WCAG "
    "principles (Perceivable, Operable, Understandable, Robust). Combines deterministic checks (axe-core rule "
    "scans, color contrast measurement, simulated keyboard tab-order/focus-trap testing) with scoped AI judgment "
    "calls evaluating each finding from the perspective of a screen reader user (NVDA/JAWS/VoiceOver) - whether "
    "the accessible name, role, state, and reading order actually produce a usable non-visual experience, not "
    "just whether markup is technically present. Every finding below cites the specific success criterion, "
    "conformance level, and severity, with reproduction steps and a remediation suggestion."
)


class AuditNotReadyError(DomainError):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"Audit run is not complete yet (status={status!r})")


def start_audit(db: Session, project: Project, page_id: int, conformance_level: str) -> AuditRun:
    page = audit_repository.get_page(db, page_id)
    if page is None or page.project_id != project.id:
        raise NotFoundError("Page not found in this project")
    return audit_repository.create_run(
        db, project_id=project.id, page_id=page.id, conformance_level=conformance_level
    )


def start_batch_audit(
    db: Session, project: Project, page_ids: list[int], conformance_level: str
) -> tuple[AuditExecution, list[tuple[int, AuditRun | None, str | None]]]:
    """Create ONE AuditExecution for this "Audit Selected Pages" click, plus
    one AuditRun per page linked to it via execution_id - this is what makes
    N selected pages a single execution/report instead of N independent ones.
    Each per-page AuditRun still runs its own Perceive->Plan->Execute->
    Reflect->Learn background job (that pipeline is inherently per-page),
    but they're now grouped so status/results can be read as one unit.

    Returns (execution, [(page_id, run, error), ...]) - a bad id in the
    batch reports as an error for that page instead of failing the batch."""
    execution = audit_repository.create_execution(
        db, project_id=project.id, conformance_level=conformance_level, total_pages=len(page_ids)
    )

    results: list[tuple[int, AuditRun | None, str | None]] = []
    for page_id in page_ids:
        page = audit_repository.get_page(db, page_id)
        if page is None or page.project_id != project.id:
            results.append((page_id, None, "Page not found in this project"))
            continue
        run = audit_repository.create_run(
            db,
            project_id=project.id,
            page_id=page.id,
            conformance_level=conformance_level,
            execution_id=execution.id,
        )
        results.append((page_id, run, None))
    return execution, results


async def run_audit_job(run_id: int) -> None:
    """Background task entry point - the single seam into app/ai/.

    On Windows, `uvicorn --reload` forces asyncio onto WindowsSelectorEventLoop
    (see uvicorn.config.Config.use_subprocess), which cannot spawn
    subprocesses - breaking Playwright's Chromium launch. run_audit only
    touches a synchronous (non-loop-bound) db.Session plus Playwright/LLM
    calls, so it's safe to run the whole job on a dedicated thread with its
    own ProactorEventLoop instead, leaving the server's main loop untouched.
    """
    if sys.platform == "win32":
        await asyncio.get_event_loop().run_in_executor(None, _run_audit_with_proactor_loop, run_id)
    else:
        await run_audit(run_id)


def _run_audit_with_proactor_loop(run_id: int) -> None:
    loop = asyncio.ProactorEventLoop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_audit(run_id))
    finally:
        loop.close()


def get_run_or_raise(db: Session, run_id: int, user_id: int) -> AuditRun:
    run = audit_repository.get_run_owned_by_user(db, run_id, user_id)
    if run is None:
        raise NotFoundError("Audit run not found")
    return run


def get_run_with_steps(db: Session, run_id: int, user_id: int) -> tuple[AuditRun, list[PlanStep]]:
    run = get_run_or_raise(db, run_id, user_id)
    steps = audit_repository.list_plan_steps(db, run_id)
    return run, steps


def get_execution_or_raise(db: Session, execution_id: int, user_id: int) -> AuditExecution:
    execution = audit_repository.get_execution_owned_by_user(db, execution_id, user_id)
    if execution is None:
        raise NotFoundError("Audit execution not found")
    return execution


def _execution_aggregate_status(statuses: set[str]) -> str:
    if not statuses or statuses <= {"queued"}:
        return "queued"
    if statuses <= {"completed"}:
        return "completed"
    if statuses <= {"failed"}:
        return "failed"
    if statuses <= TERMINAL_STATUSES:
        return "partial"
    return "running"


def get_execution_status(db: Session, execution_id: int, user_id: int) -> dict:
    """Aggregate status for a whole execution - the single thing the UI
    polls (instead of N independent per-run polls), with one progress row
    per page computed from that page's own AuditRun."""
    execution = get_execution_or_raise(db, execution_id, user_id)
    runs = audit_repository.list_runs_for_execution(db, execution_id)

    pages = [
        {
            "page_id": run.page_id,
            "page_url": run.page.url if run.page else "",
            "audit_run_id": run.id,
            "status": run.status,
            "total_steps": run.total_steps,
            "completed_steps": run.completed_steps,
            "error": run.error,
            "message": None,
        }
        for run in runs
    ]

    return {
        "execution_id": execution.id,
        "project_id": execution.project_id,
        "conformance_level": execution.conformance_level,
        "status": _execution_aggregate_status({run.status for run in runs}),
        "total_pages": execution.total_pages,
        "completed_pages": sum(1 for run in runs if run.status in TERMINAL_STATUSES),
        "created_at": execution.created_at,
        "pages": pages,
    }


def get_execution_results(db: Session, execution_id: int, user_id: int) -> dict:
    """The single combined report for a whole execution: one merged list of
    test cases/defects spanning every page, with one aggregated conformance
    summary - the counterpart to get_results() for a single-page run."""
    execution = get_execution_or_raise(db, execution_id, user_id)
    runs = audit_repository.list_runs_for_execution(db, execution_id)

    non_terminal = [run for run in runs if run.status not in TERMINAL_STATUSES]
    if non_terminal:
        raise AuditNotReadyError(non_terminal[0].status)

    page_summaries: list[dict] = []
    all_rows: list[dict] = []
    all_defects: list[dict] = []
    executive_summaries: list[str] = []
    low_confidence_ids: list[str] = []
    contradictions: list[dict] = []

    for run in runs:
        page_url = run.page.url if run.page else ""
        page_title = _page_title(run)

        if run.status != "completed":
            page_summaries.append(
                {
                    "page_id": run.page_id,
                    "audit_run_id": run.id,
                    "page_title": page_title,
                    "page_url": page_url,
                    "status": run.status,
                    "error": run.error,
                }
            )
            continue

        steps = audit_repository.list_plan_steps(db, run.id)
        rows = _build_test_cases(run, steps, page_title, page_url)
        defects = _build_defects(rows, steps)
        all_rows.extend(rows)
        all_defects.extend(defects)

        reflection_data = run.reflection_data or {}
        low_confidence_step_ids = set(reflection_data.get("low_confidence_plan_step_ids", []))
        low_confidence_ids.extend(
            row["test_case_id"] for row, step in zip(rows, steps) if step.id in low_confidence_step_ids
        )
        contradictions.extend(
            {**c, "page_id": run.page_id, "page_url": page_url} for c in reflection_data.get("contradictions", [])
        )
        if run.reflection_summary:
            executive_summaries.append(f"{page_title or page_url}: {run.reflection_summary}")

        page_total = len(rows)
        page_passed = sum(1 for row in rows if row["status"] == "pass")
        page_summaries.append(
            {
                "page_id": run.page_id,
                "audit_run_id": run.id,
                "page_title": page_title,
                "page_url": page_url,
                "status": run.status,
                "total_test_cases": page_total,
                "total_defects": len(defects),
                "pass_rate": round((page_passed / page_total) * 100, 1) if page_total else 0.0,
            }
        )

    completed_page_count = sum(1 for p in page_summaries if p.get("total_test_cases") is not None)

    return {
        "execution_id": execution.id,
        "project_id": execution.project_id,
        "status": _execution_aggregate_status({run.status for run in runs}),
        "conformance_level": execution.conformance_level,
        "pages": page_summaries,
        "low_confidence_test_case_ids": low_confidence_ids,
        "contradictions": contradictions,
        "report": _build_combined_report(execution, all_rows, all_defects, executive_summaries),
        "test_cases": all_rows,
        "defects": all_defects,
        # Not part of AuditExecutionResultsOut (Pydantic silently drops
        # unknown keys) - only read by build_word_report/build_excel_report,
        # which take this raw dict, to label the combined document.
        "project_name": execution.project.name if execution.project else "",
        "page_title": f"{completed_page_count} page(s)",
        "page_url": ", ".join(p["page_url"] for p in page_summaries if p.get("page_url")),
    }


def override_step(
    db: Session, run_id: int, plan_step_id: int, user_id: int, *, status: str | None, defect_status: str | None
) -> PlanStep:
    """Apply a human reviewer's correction to one test case's verdict and/or
    a defect's lifecycle status. Ownership is checked via the parent audit
    run (plan steps have no owner of their own) so a user can't PATCH a
    step belonging to someone else's run even by guessing its id."""
    run = get_run_or_raise(db, run_id, user_id)
    step = audit_repository.get_plan_step(db, plan_step_id)
    if step is None or step.audit_run_id != run.id:
        raise NotFoundError("Test case not found in this audit run")
    updated = audit_repository.update_plan_step_override(db, plan_step_id, status=status, defect_status=defect_status)
    assert updated is not None  # already confirmed to exist above
    return updated


def get_results(db: Session, run_id: int, user_id: int) -> dict:
    """Everything AuditResultsOut needs, as a plain dict the view can pass
    straight to `AuditResultsOut(**...)` - test cases, the defects subset,
    and the deterministically-computed IAAP-style report summary."""
    run = get_run_or_raise(db, run_id, user_id)
    if run.status not in TERMINAL_STATUSES:
        raise AuditNotReadyError(run.status)

    steps = audit_repository.list_plan_steps(db, run_id)
    page_title = _page_title(run)
    page_url = run.page.url if run.page else ""

    rows = _build_test_cases(run, steps, page_title, page_url)
    defects = _build_defects(rows, steps)
    report = _build_report(run, rows, defects)

    reflection_data = run.reflection_data or {}
    low_confidence_step_ids = set(reflection_data.get("low_confidence_plan_step_ids", []))
    low_confidence_test_case_ids = [
        row["test_case_id"] for row, step in zip(rows, steps) if step.id in low_confidence_step_ids
    ]
    contradictions = reflection_data.get("contradictions", [])

    return {
        "audit_run_id": run.id,
        "page_id": run.page_id,
        "project_name": run.project.name if run.project else "",
        "page_title": page_title,
        "page_url": page_url,
        "status": run.status,
        "conformance_level": run.conformance_level,
        "low_confidence_test_case_ids": low_confidence_test_case_ids,
        "contradictions": contradictions,
        "report": report,
        "test_cases": rows,
        "defects": defects,
    }


def _page_title(run: AuditRun) -> str:
    perception = run.perception or {}
    return perception.get("title") or (run.page.page_title if run.page else None) or ""


# ── Test Case sheet mapping ──────────────────────────────────────────────

def _severity(plan_step: PlanStep, status: str, evidence: dict) -> str:
    if status == "pass":
        return "N/A"
    if status == "needs_review":
        return "Review Needed"

    violations = evidence.get("violations") if isinstance(evidence, dict) else None
    if violations:
        impacts = [v.get("impact") for v in violations if v.get("impact") in _SEVERITY_BY_AXE_IMPACT]
        if impacts:
            worst = min(impacts, key=_AXE_IMPACT_ORDER.index)
            return _SEVERITY_BY_AXE_IMPACT[worst]

    return "High" if plan_step.level == "A" else "Medium"


# Per-criterion description of the ideal screen reader experience — what the user
# *should hear* when the page is fully accessible. Keyed by WCAG success criterion.
_SR_EXPECTED = {
    "1.1.1": (
        "When a screen reader (NVDA/JAWS/VoiceOver) reaches an image, it should announce a meaningful "
        "description of the image's content or function — e.g. 'Company logo: WinVinaya' or 'Submit'. "
        "Decorative images should be silently skipped (alt=\"\" or role=\"presentation\")."
    ),
    "1.3.1": (
        "A screen reader should announce headings, lists, tables, and form labels with their correct "
        "semantic role — e.g. 'Heading level 2: Products', 'Table: Pricing'. Structure conveyed visually "
        "must also be conveyed through markup so the non-visual reading order makes sense."
    ),
    "1.3.2": (
        "When navigating linearly (Down Arrow or Tab) with a screen reader, the content should be "
        "announced in a logical sequence that matches the visual reading order. No content should appear "
        "out of order or be skipped due to a mismatch between DOM order and CSS positioning."
    ),
    "1.3.3": (
        "Instructions must not rely solely on shape, color, or position — the screen reader user should "
        "be able to follow directions without needing to see the page layout."
    ),
    "1.4.1": (
        "Information conveyed by color alone (e.g. 'required fields are red') must also be communicated "
        "through text or an ARIA label that the screen reader announces — e.g. 'Email (required)'."
    ),
    "1.4.3": (
        "Text should have sufficient contrast so that low-vision users can read it without assistive "
        "technology. For screen reader users, the text must also be programmatically accessible."
    ),
    "1.4.11": (
        "Non-text UI components (icons, input borders, focus rings) must have sufficient contrast against "
        "adjacent colors so that keyboard and low-vision users can identify interactive elements."
    ),
    "2.1.1": (
        "Every interactive element — links, buttons, form controls, menus — must be reachable and "
        "operable using the Tab / Shift+Tab / Enter / Space / Arrow keys alone, without a mouse. "
        "A screen reader user navigating by Tab should be able to activate all functionality."
    ),
    "2.1.2": (
        "A screen reader or keyboard user must be able to move focus away from every component using "
        "standard keys (Escape, Tab). No 'keyboard trap' should prevent navigation away from a widget."
    ),
    "2.4.1": (
        "A 'Skip to main content' link (or equivalent landmark navigation) should be announced as the "
        "first focusable element. Screen reader users should be able to jump past repeated navigation "
        "blocks with a single keypress and land directly in the main content area."
    ),
    "2.4.3": (
        "When tabbing through the page, focus should move in an order that matches the visual/reading "
        "sequence. A screen reader user should encounter links, buttons, and form fields in a logical "
        "top-to-bottom, left-to-right order."
    ),
    "2.4.4": (
        "Every link's accessible name must describe its destination or purpose unambiguously when read "
        "out of context by a screen reader — e.g. 'Read more about Accessibility Services', not just "
        "'Read more' or 'Click here'."
    ),
    "2.4.6": (
        "Headings and labels must describe the content that follows. When a screen reader user lists "
        "headings (NVDA: Insert+F7, JAWS: Insert+F6), each heading should give a clear idea of the "
        "section's topic."
    ),
    "2.4.7": (
        "When Tab focus lands on any interactive element, the screen reader user must be able to see "
        "(or their sighted companion must be able to see) a clearly visible focus indicator — a visible "
        "outline or highlight that shows where keyboard focus currently is."
    ),
    "3.3.1": (
        "When a form is submitted with errors, a screen reader should announce each field in error and "
        "describe the specific problem — e.g. 'Email: Error — Please enter a valid email address'. "
        "Errors must not be conveyed by color or icon alone."
    ),
    "3.3.2": (
        "Every form input must have a visible, programmatically-associated label that a screen reader "
        "announces when focus enters the field — e.g. 'First name, edit text'. Placeholder text alone "
        "is not an acceptable label."
    ),
    "3.3.3": (
        "When a screen reader user submits a form with errors, the error message should include a "
        "specific correction suggestion — e.g. 'Date of birth: Error — Please use the format DD/MM/YYYY'."
    ),
    "4.1.2": (
        "Every interactive UI component must expose an accessible name, role, and value to the "
        "screen reader — e.g. a toggle button should be announced as 'Dark mode, toggle button, pressed' "
        "or 'Dark mode, toggle button, not pressed' so the user knows its current state."
    ),
    "4.1.3": (
        "When page content changes dynamically (alerts, status messages, live regions), a screen reader "
        "should automatically announce the change — e.g. 'Form submitted successfully' — without "
        "requiring the user to manually navigate to the updated region."
    ),
}

_SR_EXPECTED_FALLBACK = (
    "A screen reader user (NVDA/JAWS/VoiceOver) should be able to perceive, operate, and understand "
    "this element without any visual reference. The accessible name, role, state, and reading order "
    "must produce a usable, non-visual experience that satisfies WCAG {criterion} ({name})."
)

# Per-criterion, element-specific clause appended after the general _SR_EXPECTED boilerplate.
# Written as a sentence that completes: "For this specific element — <X> — ..."
_ELEMENT_EXPECTED_CLAUSES: dict[str, str] = {
    "1.1.1": (
        "a meaningful alt attribute must be present that describes its content or function "
        "(e.g., alt=\"Company logo\"). If it is purely decorative, it must have alt=\"\" or "
        "role=\"presentation\" so screen readers silently skip it."
    ),
    "1.3.1": (
        "semantic HTML or ARIA markup must correctly expose its structure — heading level, list, "
        "table role, or form label — so assistive technology announces it with the right role."
    ),
    "1.3.2": (
        "it must appear in the DOM in a logical reading order that matches the visual layout, "
        "so a screen reader navigating linearly encounters it in the expected sequence."
    ),
    "1.3.3": (
        "any instructions or cues associated with it must not rely solely on shape, color, "
        "size, or position — the meaning must be conveyed in text."
    ),
    "1.4.1": (
        "information it conveys through color must also be provided through text, an icon, "
        "or an ARIA label that a screen reader can announce."
    ),
    "1.4.3": (
        "the text contrast ratio against its background must meet WCAG minimums: "
        "4.5:1 for normal text, 3:1 for large text (18pt or 14pt bold)."
    ),
    "1.4.11": (
        "the component's boundary or focus indicator must have a contrast ratio of at least 3:1 "
        "against adjacent colors so keyboard and low-vision users can identify it."
    ),
    "2.1.1": (
        "it must be fully operable using only the keyboard (Tab, Enter, Space, Arrow keys) "
        "without requiring a mouse or touch gesture."
    ),
    "2.1.2": (
        "keyboard focus must be moveable away from it using standard keys (Tab or Escape) — "
        "it must not trap the keyboard user inside it."
    ),
    "2.4.1": (
        "a skip link or landmark region must be present and functional, allowing screen reader "
        "and keyboard users to bypass it and jump directly to the main content."
    ),
    "2.4.3": (
        "focus must arrive at it in a logical order matching the visual and reading sequence, "
        "so the user encounters elements top-to-bottom and left-to-right."
    ),
    "2.4.4": (
        "its accessible name (link text) must describe the destination or purpose clearly when "
        "read out of context — e.g. 'Read more about Accessibility Services', not 'Click here'."
    ),
    "2.4.6": (
        "its heading or label text must clearly describe the section or field it introduces, "
        "so screen reader users navigating by headings understand the page structure."
    ),
    "2.4.7": (
        "a clearly visible focus indicator (outline or highlight) must appear when it receives "
        "keyboard focus, so sighted keyboard users can see where they are on the page."
    ),
    "3.3.1": (
        "any error associated with it must identify the specific field in error and describe "
        "the problem in text — not through color or icon alone."
    ),
    "3.3.2": (
        "it must have a visible, programmatically-associated label that a screen reader "
        "announces when focus enters the field — placeholder text alone is not sufficient."
    ),
    "3.3.3": (
        "the error message for it must include a specific correction suggestion "
        "(e.g., 'Please use the format DD/MM/YYYY'), not just a generic error notice."
    ),
    "4.1.2": (
        "it must expose an accessible name, role, and current value/state to assistive technology "
        "— e.g., a toggle button must announce 'Dark mode, toggle button, pressed' or 'not pressed'."
    ),
    "4.1.3": (
        "any dynamic content change it triggers must be announced automatically to screen readers "
        "via aria-live or role=\"status\"/\"alert\" — without requiring the user to navigate to the update."
    ),
}


def _find_relevant_violation(plan_step: PlanStep, evidence: dict) -> dict | None:
    """Return the single axe-core violation dict that is most relevant to this
    plan step, or None if nothing in `evidence` actually tests this step's
    WCAG criterion.

    Matching priority (first match wins):
      1. violation whose rule_id is in target_element.axe_rule_ids
      2. violation whose rule_id is in WCAG_TO_AXE_RULES[plan_step.wcag_criterion]
         (deterministic backstop for when the LLM planner didn't set
         axe_rule_ids, or set one that doesn't match anything in evidence)
      3. violation containing a node whose target CSS matches
         target_element.selector (substring match)

    Deliberately NOT returning violations[0] as a last-resort fallback: that
    was the root cause of the color-contrast/region mis-binding bug. axe can
    return violations for rules that have nothing to do with this step's
    criterion (e.g. a global/unscoped run, or a page with a color-contrast
    issue elsewhere); silently stamping an unrelated violation onto this row
    is worse than reporting no violation detail at all. Callers must treat
    None as "no axe evidence directly ties to this criterion" and fall back
    to the step's `status`/`reasoning`, not invent a rule match.
    """
    if not isinstance(evidence, dict):
        return None
    violations = evidence.get("violations")
    if not violations:
        return None

    target = plan_step.target_element or {}

    # Strategy 1: match by axe rule_id(s) the LLM planner attached to this step
    desired_rules = set(target.get("axe_rule_ids") or [])

    # Strategy 1.5: backstop with the deterministic WCAG -> axe rule table,
    # in case axe_rule_ids is missing/wrong for this criterion.
    desired_rules |= set(axe_rules_for_criterion(getattr(plan_step, "wcag_criterion", None) or ""))

    if desired_rules:
        for v in violations:
            if v.get("rule_id") in desired_rules:
                return v

    # Strategy 2: match by target selector substring in any node's target list
    selector = target.get("selector") or target.get("context_selector") or ""
    if selector:
        for v in violations:
            for node in v.get("nodes", []):
                targets = node.get("target") or []
                # targets is a list of CSS selector strings from axe
                if any(selector in t for t in targets):
                    return v

    return None


def _describe_stop(stop: dict) -> str:
    """Human-readable identification of one keyboard_nav tab stop, e.g.
    "<button> .menu-toggle ('Open menu')" - enough for a developer to find
    it in the DOM without re-running the simulation themselves."""
    label = f" ({stop['label']!r})" if stop.get("label") else ""
    return f"<{stop['tag']}> {stop['selector']}{label}"


def _keyboard_flagged_stop(evidence: dict) -> dict | None:
    """The one tab stop keyboard_nav_tool's evidence actually flagged as a
    problem, so report fields can name a specific element instead of only
    reporting an aggregate stop_count. None for a clean pass."""
    if not isinstance(evidence, dict) or "stops" not in evidence:
        return None
    if evidence.get("trap_detected") and evidence.get("stops"):
        return evidence["stops"][-1]
    if evidence.get("reordering_flags"):
        return evidence["reordering_flags"][0]["to"]
    if evidence.get("invisible_focus_targets"):
        return evidence["invisible_focus_targets"][0]
    return None


def _element_label(plan_step: PlanStep, evidence: dict, violation: dict | None = None) -> str:
    """Best available human-readable label for the specific element being tested.

    Pass `violation` (from _find_relevant_violation) to use a pre-scoped
    violation rather than re-fetching from evidence; this ensures Description,
    Expected, Actual, and HTML Snippet all reference the same element.

    Priority:
      1. Node HTML from the supplied (pre-scoped) violation
      2. direct html/target_html evidence field
      3. the specific tab stop keyboard_nav flagged as a problem (evidence
         carries the full stop list/flags, not just a count - see
         _keyboard_flagged_stop), so a keyboard finding names an element
         instead of describing "the whole page"
      4. target_element.description (LLM-authored free-text description)
      5. target_element.selector (CSS selector) - unless it's a comma-
         separated selector *list* (e.g. "button, p, span"), which names a
         set of elements, not one specific instance, and would mislead a
         developer into thinking exactly one thing was measured
      6. plan_step.title (the specific per-instance test case name, e.g.
         "Anoop's profile photo missing alt text" - always more specific
         than the generic element_type category, so it comes before that)
      7. element_type taxonomy label (generic category - last resort before
         the hardcoded fallback, since it names a class of element, not
         the specific instance under test)
      8. hard fallback 'the element'
    """
    if violation is not None:
        nodes = violation.get("nodes", [])
        if nodes:
            html = nodes[0].get("html", "")
            if html:
                return html[:150] + ("\u2026" if len(html) > 150 else "")
    if isinstance(evidence, dict):
        for key in ("html", "target_html"):
            val = evidence.get(key)
            if val:
                return val[:150] + ("\u2026" if len(val) > 150 else "")
        flagged_stop = _keyboard_flagged_stop(evidence)
        if flagged_stop:
            return _describe_stop(flagged_stop)
    target = plan_step.target_element or {}
    if target.get("description"):
        return target["description"]
    selector = target.get("selector")
    if selector and "," not in selector:
        return selector
    if plan_step.title:
        return plan_step.title
    return plan_step.element_type or "the element"


def _expected_result(plan_step: PlanStep, violation: dict | None, evidence: dict) -> str:
    """Element-specific expected result: general criterion guidance + what this element must do.

    `violation` is the pre-scoped violation from _find_relevant_violation so
    all fields in a row reference the same element, not whatever happened to
    be violations[0] in the stored evidence.
    """
    element = _element_label(plan_step, evidence, violation)
    base = _SR_EXPECTED.get(plan_step.wcag_criterion)
    if not base:
        name = criterion_name(plan_step.wcag_criterion)
        base = _SR_EXPECTED_FALLBACK.format(criterion=plan_step.wcag_criterion, name=name)
    specific_clause = _ELEMENT_EXPECTED_CLAUSES.get(
        plan_step.wcag_criterion,
        "it must satisfy the accessibility requirement described above.",
    )
    return (
        f"{base}\n\n"
        f"For this specific element — {element} — {specific_clause}"
    )


def _actual_result(
    plan_step: PlanStep, status: str, reasoning: str, evidence: dict, violation: dict | None
) -> str:
    """Element-specific description of what actually happens with a screen reader.

    `violation` is the pre-scoped violation from _find_relevant_violation.
    Bug fixed: previously read violations[0].get("id") but axe_tool.py stores
    the field as "rule_id" not "id", causing the empty-rule-ID symptom.
    """
    element = _element_label(plan_step, evidence, violation)
    name = criterion_name(plan_step.wcag_criterion)

    if status == "pass":
        return (
            f"The element '{element}' correctly satisfies WCAG {plan_step.wcag_criterion} ({name}). "
            f"It is properly exposed to assistive technology and screen reader testing confirmed no barrier. "
            f"Detail: {reasoning}"
        )
    if status == "needs_review":
        return (
            f"The element '{element}' could not be automatically classified against "
            f"WCAG {plan_step.wcag_criterion} ({name}). "
            f"Manual screen reader testing (NVDA/JAWS/VoiceOver) is required to determine whether "
            f"a real-world user would encounter a barrier at this element. "
            f"AI finding: {reasoning}"
        )
    # status == "fail" — extract axe-core violation detail from the pre-scoped violation.
    # Key is "rule_id" (set by axe_tool.py), NOT "id" (raw axe-core JSON key).
    violation_detail = ""
    if violation is not None:
        rule_id = violation.get("rule_id", "")
        vdesc = violation.get("description", "") or violation.get("help", "")
        if rule_id and vdesc:
            violation_detail = f" Axe-core rule '{rule_id}' reports: {vdesc}."
        elif vdesc:
            violation_detail = f" {vdesc}."
    return (
        f"The element '{element}' fails WCAG {plan_step.wcag_criterion} ({name})."
        f"{violation_detail} "
        f"A screen reader user (NVDA/JAWS/VoiceOver) navigating to this element would encounter "
        f"an accessibility barrier. Finding: {reasoning}"
    )


def _steps_to_reproduce(page_url: str, plan_step: PlanStep, element: str) -> str:
    """Numbered reproduction steps written for a screen reader user.

    `element` is the same resolved label _description/_expected_result/
    _actual_result use (from _element_label) - previously this rebuilt its
    own, less-specific version straight from target_element, which let
    Description name a real DOM element while Steps to Reproduce still said
    something generic like "entire page keyboard navigation".
    """
    if plan_step.method == "tool":
        return (
            f"1. Open {page_url} in Chrome or Firefox.\n"
            f"2. Run the automated '{plan_step.tool_name}' accessibility check targeting: {element}.\n"
            f"3. Review the violations list and compare each flagged element against the Expected Result above.\n"
            f"4. To confirm impact on real users, also enable a screen reader (NVDA on Windows, "
            f"VoiceOver on macOS) and navigate to the flagged element — listen to what is announced."
        )
    return (
        f"1. Open {page_url} in Chrome or Firefox.\n"
        f"2. Enable a screen reader: NVDA (Windows) — press Ctrl+Alt+N to start; "
        f"or VoiceOver (macOS) — press Cmd+F5; or TalkBack (Android) — activate via Accessibility settings.\n"
        f"3. Navigate to {element} using the Tab key (interactive elements) "
        f"or the screen reader's element navigator (NVDA: Insert+F7 for element list).\n"
        f"4. Listen to what the screen reader announces for this element.\n"
        f"5. Compare the announcement against the Expected Result above — "
        f"note any missing information, incorrect role/state, or confusing reading order.\n"
        f"6. Evaluate against WCAG {plan_step.wcag_criterion} ({criterion_name(plan_step.wcag_criterion)})."
    )


def _html_snippet(evidence: dict, violation: dict | None = None) -> str | None:
    """Return the HTML snippet for the pre-scoped violation (not violations[0]).

    `violation` is from _find_relevant_violation so this snippet is
    guaranteed to match the same element used in Description/Expected/Actual.
    """
    if violation is not None:
        nodes = violation.get("nodes", [])
        if nodes:
            return nodes[0].get("html")
    if isinstance(evidence, dict):
        flagged_stop = _keyboard_flagged_stop(evidence)
        if flagged_stop and flagged_stop.get("html"):
            return flagged_stop["html"]
    return evidence.get("html") or evidence.get("target_html")


def _suggestion_to_fix(plan_step: PlanStep, status: str, evidence: dict | None = None, violation: dict | None = None) -> str:
    """Remediation text - includes the actual measured values (ratio, colors,
    flagged element) when they're available in evidence, not just a generic
    per-criterion boilerplate sentence, so a developer knows the concrete
    current-vs-required numbers instead of having to re-measure themselves."""
    if status == "needs_review":
        element = _element_label(plan_step, evidence or {}, violation)
        return (
            f"AI confidence was too low to auto-classify '{element}' - review manually against WCAG "
            f"{plan_step.wcag_criterion} ({criterion_name(plan_step.wcag_criterion)})."
        )

    base = _REMEDIATION_HINTS.get(
        plan_step.wcag_criterion,
        f"Review and correct the page to satisfy WCAG {plan_step.wcag_criterion} ({criterion_name(plan_step.wcag_criterion)}).",
    )

    detail = ""
    if violation is not None:
        nodes = violation.get("nodes", [])
        failure_summary = nodes[0].get("failure_summary") if nodes else None
        if failure_summary:
            detail = f" axe-core detail: {failure_summary}"
    elif isinstance(evidence, dict):
        if "ratio" in evidence and "required_ratio" in evidence:
            detail = (
                f" Measured contrast is {evidence['ratio']}:1 ({evidence.get('foreground', '?')} text on "
                f"{evidence.get('background', '?')} background) - needs at least {evidence['required_ratio']}:1."
            )
        else:
            flagged_stop = _keyboard_flagged_stop(evidence)
            if flagged_stop:
                if evidence.get("trap_detected"):
                    detail = f" Focus trap at {_describe_stop(flagged_stop)} - ensure focus can move past it with Tab/Shift+Tab."
                elif evidence.get("reordering_flags"):
                    detail = f" Fix DOM/tabindex order so {_describe_stop(flagged_stop)} is reached in visual/reading order."
                elif evidence.get("invisible_focus_targets"):
                    detail = f" {_describe_stop(flagged_stop)} receives focus but isn't visible - ensure it scrolls into view or isn't focusable while hidden."

    return base + detail


def _description(plan_step: PlanStep, evidence: dict, violation: dict | None) -> str:
    """Element-specific test case description — tells the reader exactly what is being checked
    and which element is under test, so a developer can immediately locate the issue.

    `violation` is from _find_relevant_violation so the element label matches
    the one used in Expected Result, Actual Result, and HTML Snippet.
    """
    name = criterion_name(plan_step.wcag_criterion)
    element = _element_label(plan_step, evidence, violation)
    method_str = (
        f"automated '{plan_step.tool_name}' rule"
        if plan_step.method == "tool" and plan_step.tool_name
        else "AI judgment"
    )
    return (
        f"Tests that '{element}' satisfies WCAG {plan_step.wcag_criterion} ({name}) "
        f"using {method_str}. "
        f"Test: {plan_step.title}."
    )


def _build_test_cases(run: AuditRun, plan_steps: list[PlanStep], page_title: str, page_url: str) -> list[dict]:
    rows: list[dict] = []

    for step in plan_steps:
        latest = step.results[-1] if step.results else None
        ai_status = latest.status if latest else "needs_review"
        # A human reviewer's override (see PATCH /plan-steps/{id}) wins over the
        # AI-derived verdict - it's a correction, not something to discard.
        status = step.manual_status_override or ai_status
        confidence = latest.confidence if latest else 0.0
        evidence = latest.evidence if latest else {}
        reasoning = (latest.reasoning if latest else None) or "This step did not complete."
        name = criterion_name(step.wcag_criterion)

        # Resolve the ONE violation most relevant to this step ONCE and share it
        # across all four text fields. This is the single source of truth that
        # prevents Description/Expected/Actual/HTML Snippet from diverging.
        # Before this fix, every helper re-fetched violations[0] independently,
        # which caused all rows in a global axe run to inherit the first DOM
        # element (usually the skip-link or contrast element).
        violation = _find_relevant_violation(step, evidence)

        # Resolved once and passed into every field that names the element
        # (_description computes the identical value internally from the same
        # inputs) so Description and Steps to Reproduce can never diverge -
        # previously _steps_to_reproduce rebuilt its own weaker version
        # straight from target_element, which is exactly the class of
        # mismatch a since-removed self-check here used to just log and export anyway.
        element = _element_label(step, evidence, violation)

        desc = _description(step, evidence, violation)
        steps_repr = _steps_to_reproduce(page_url, step, element)

        rows.append(
            {
                "test_case_id": f"TC-{run.id}-{step.step_order:03d}",
                "audit_run_id": run.id,
                "plan_step_id": step.id,
                "tc_name": step.title,
                "page_id": run.page_id,
                "page_title": page_title,
                "page_url": page_url,
                "principle": principle_for_criterion(step.wcag_criterion),
                "criteria": f"{step.wcag_criterion} {name}",
                "level": step.level,
                "element_type": step.element_type,
                "severity": _severity(step, status, evidence),
                "status": status,
                "description": desc,
                "expected_result": _expected_result(step, violation, evidence),
                "actual_result": _actual_result(step, status, reasoning, evidence, violation),
                "steps_to_reproduce": steps_repr,
                "remediation": _suggestion_to_fix(step, status, evidence, violation) if status != "pass" else "",
                "html_snippet": _html_snippet(evidence, violation),
                "screenshot": evidence.get("screenshot_path"),
                "confidence": confidence,
                "is_low_confidence": confidence < settings.AI_LOW_CONFIDENCE_THRESHOLD,
                "reasoning": reasoning,
            }
        )
    return rows


def _build_defects(rows: list[dict], plan_steps: list[PlanStep]) -> list[dict]:
    """The failed/needs-review subset of test cases, renumbered as defects
    and reshaped to the Defects sheet's field names. `rows` and `plan_steps`
    are built from (and stay in) the same order, so zipping them is safe."""
    defects: list[dict] = []
    seq = 0
    for row, step in zip(rows, plan_steps):
        if row["status"] == "pass":
            continue
        seq += 1
        defects.append(
            {
                "defect_id": f"DEF-{step.audit_run_id}-{seq:03d}",
                "test_case_id": row["test_case_id"],
                "audit_run_id": row["audit_run_id"],
                "plan_step_id": row["plan_step_id"],
                "page_id": row["page_id"],
                "page_title": row["page_title"],
                "page_url": row["page_url"],
                "principle": row["principle"],
                "criteria": row["criteria"],
                "level": row["level"],
                "element_type": row["element_type"],
                "severity": row["severity"],
                "status": row["status"],
                # Severity/Status describe the finding; this describes how much to
                # trust it. A client summing severities across a whole report must
                # be able to tell "confirmed by a deterministic tool" apart from
                # "the AI wasn't sure and a human hasn't looked yet" - conflating
                # the two under one Severity value was the bug: an unconfirmed
                # needs_review item would silently count the same as a verified one.
                "verification_status": "Confirmed" if row["status"] == "fail" else "AI Judgment - Needs Review",
                "defect_status": step.defect_status,
                "description": row["description"],
                "expected_result": row["expected_result"],
                "actual_result": row["actual_result"],
                "steps_to_reproduce": row["steps_to_reproduce"],
                "suggestion_to_fix": row["remediation"],
                "html_snippet": row["html_snippet"],
                "screenshot": row["screenshot"],
                "confidence": row["confidence"],
                "is_low_confidence": row["is_low_confidence"],
            }
        )
    return defects


def _breakdown(rows: list[dict], key: str) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        label = row[key]
        bucket = buckets.setdefault(label, {"label": label, "total": 0, "passed": 0, "failed": 0, "needs_review": 0})
        bucket["total"] += 1
        if row["status"] == "pass":
            bucket["passed"] += 1
        elif row["status"] == "fail":
            bucket["failed"] += 1
        else:
            bucket["needs_review"] += 1
    return list(buckets.values())


def _build_report(run: AuditRun, rows: list[dict], defects: list[dict]) -> dict:
    total = len(rows)
    passed = sum(1 for row in rows if row["status"] == "pass")
    pass_rate = round((passed / total) * 100, 1) if total else 0.0

    severity_counts: dict[str, int] = {}
    for defect in defects:
        severity_counts[defect["severity"]] = severity_counts.get(defect["severity"], 0) + 1

    return {
        "methodology": _METHODOLOGY_TEMPLATE.format(level=run.conformance_level),
        "executive_summary": run.reflection_summary,
        "total_test_cases": total,
        "total_defects": len(defects),
        "pass_rate": pass_rate,
        "by_principle": _breakdown(rows, "principle"),
        "by_level": _breakdown(rows, "level"),
        "by_severity": severity_counts,
    }


def _build_combined_report(
    execution: AuditExecution, rows: list[dict], defects: list[dict], executive_summaries: list[str]
) -> dict:
    """Same shape as _build_report, but aggregated across every completed
    page's rows in one execution instead of a single run's."""
    total = len(rows)
    passed = sum(1 for row in rows if row["status"] == "pass")
    pass_rate = round((passed / total) * 100, 1) if total else 0.0

    severity_counts: dict[str, int] = {}
    for defect in defects:
        severity_counts[defect["severity"]] = severity_counts.get(defect["severity"], 0) + 1

    return {
        "methodology": _METHODOLOGY_TEMPLATE.format(level=execution.conformance_level),
        "executive_summary": "\n\n".join(executive_summaries) if executive_summaries else None,
        "total_test_cases": total,
        "total_defects": len(defects),
        "pass_rate": pass_rate,
        "by_principle": _breakdown(rows, "principle"),
        "by_level": _breakdown(rows, "level"),
        "by_severity": severity_counts,
    }
