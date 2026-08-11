"""
EXECUTE stage: runs an AuditPlan's steps one at a time, in order.
Deterministic checks (contrast ratios, ARIA validity, alt-text presence,
heading structure) dispatch to tools/, never the LLM. Judgment checks (does
this alt text meaningfully describe the image, is this error message
understandable, is this focus order logical) call the LLM with a scoped,
single-purpose prompt.

Every step's result is recorded immediately via audit_repository - not
batched until the run ends - so a crash mid-run keeps whatever completed.
If a judgment step's confidence is below the low-confidence threshold and
it didn't pass, exactly one follow-up judgment step is triggered (never a
full re-run) and recorded against the same plan step, linked via
follow_up_of_id.
"""
from __future__ import annotations

import logging

from playwright.async_api import Page
from sqlalchemy.orm import Session

from app.ai import llm_client
from app.ai.prompts import judgment_prompts
from app.ai.schemas import PageSnapshot, StepResultSchema
from app.ai.tools import axe_tool, contrast_tool, keyboard_nav_tool, screenshot_tool
from app.config import settings
from app.models.plan_step import METHOD_LLM, METHOD_TOOL, PLAN_STEP_STATUS_RUNNING, PlanStep
from app.repositories import audit_repository
from app.utils import wcag_criteria

logger = logging.getLogger(__name__)

_STEP_RESULT_SCHEMA = llm_client.build_structured_schema(StepResultSchema)


async def run(
    db: Session,
    page: Page,
    plan_steps: list[PlanStep],
    snapshot: PageSnapshot,
    *,
    conformance_level: str,
    run_id: int,
) -> None:
    for step in plan_steps:
        audit_repository.update_plan_step_status(db, step.id, PLAN_STEP_STATUS_RUNNING)

        try:
            if step.method == METHOD_TOOL:
                result_schema = await _execute_tool_step(
                    page, step, snapshot, run_id=run_id, conformance_level=conformance_level
                )
            else:
                result_schema = await _execute_judgment_step(step, snapshot, conformance_level)
        except Exception as exc:  # noqa: BLE001 - one step failing must not abort the whole run
            logger.exception("Plan step %s raised while executing", step.id)
            result_schema = StepResultSchema(
                status="needs_review",
                confidence=0.0,
                evidence={"error": str(exc)[:500]},
                reasoning="Step execution raised an unexpected error and could not complete.",
            )

        original_result = audit_repository.create_step_result(
            db,
            plan_step_id=step.id,
            status=result_schema.status,
            confidence=result_schema.confidence,
            evidence=result_schema.evidence,
            reasoning=result_schema.reasoning,
        )

        needs_followup = (
            step.method == METHOD_LLM
            and result_schema.status != "pass"
            and result_schema.confidence < settings.AI_LOW_CONFIDENCE_THRESHOLD
        )
        if needs_followup:
            await _run_followup(db, step, original_result.id, snapshot, conformance_level)


async def _run_followup(db: Session, step: PlanStep, original_result_id: int, snapshot: PageSnapshot, conformance_level: str) -> None:
    """Exactly one re-check, never a full re-run: a second, independently
    framed judgment call that knows the first pass was uncertain."""
    try:
        followup_schema = await _execute_judgment_step(step, snapshot, conformance_level, is_followup=True)
    except Exception:  # noqa: BLE001
        logger.exception("Follow-up judgment call failed for plan step %s", step.id)
        return

    audit_repository.create_step_result(
        db,
        plan_step_id=step.id,
        status=followup_schema.status,
        confidence=followup_schema.confidence,
        evidence=followup_schema.evidence,
        reasoning=followup_schema.reasoning,
        is_follow_up=True,
        follow_up_of_id=original_result_id,
    )


# ── Deterministic tool dispatch ─────────────────────────────────────────

async def _execute_tool_step(
    page: Page, step: PlanStep, snapshot: PageSnapshot, *, run_id: int, conformance_level: str
) -> StepResultSchema:
    target = step.target_element or {}

    if step.tool_name == "axe":
        return await _run_axe_step(page, step, target)
    if step.tool_name == "contrast":
        return await _run_contrast_step(page, target, snapshot, conformance_level)
    if step.tool_name == "keyboard_nav":
        return await _run_keyboard_nav_step(page)
    if step.tool_name == "screenshot":
        return await _run_screenshot_step(page, target, run_id=run_id, step_order=step.step_order)

    return StepResultSchema(
        status="needs_review",
        confidence=0.0,
        evidence={"tool_name": step.tool_name},
        reasoning=f"Unknown tool '{step.tool_name}' - unable to execute this step automatically.",
    )


async def _run_axe_step(page: Page, step: PlanStep, target: dict) -> StepResultSchema:
    # planner._harden_axe_rule_ids already grounds target_element.axe_rule_ids
    # in WCAG_TO_AXE_RULES for every axe-tagged step, but fall back to the
    # table directly here too (belt-and-suspenders for steps constructed
    # outside the normal PLAN path, e.g. manually-created plan steps): never
    # run axe unscoped, since an unscoped run returns every violation on the
    # page and _find_relevant_violation would have nothing reliable to match
    # against.
    rule_ids = target.get("axe_rule_ids") or wcag_criteria.axe_rules_for_criterion(step.wcag_criterion)
    if not rule_ids:
        return StepResultSchema(
            status="needs_review",
            confidence=0.0,
            evidence={},
            reasoning=f"No axe-core rule reliably tests WCAG {step.wcag_criterion} - "
            "routed to manual/AI review instead of an unscoped axe run.",
        )

    violations = await axe_tool.run_axe(page, rule_ids=rule_ids, context_selector=target.get("context_selector"))
    if violations:
        return StepResultSchema(
            status="fail",
            confidence=1.0,
            evidence={"violations": violations},
            reasoning=f"axe-core reported {len(violations)} violation group(s) totalling "
            f"{sum(len(v['nodes']) for v in violations)} affected node(s).",
        )
    return StepResultSchema(
        status="pass",
        confidence=1.0,
        evidence={"violations": []},
        reasoning="axe-core reported no violations for the targeted rule(s).",
    )


async def _run_contrast_step(page: Page, target: dict, snapshot: PageSnapshot, conformance_level: str) -> StepResultSchema:
    selector = target.get("selector")
    if selector and "," in selector:
        # A comma makes this a CSS selector *list*, not one element - the
        # planner LLM sometimes writes "button, p, span" trying to mean
        # "several kinds of low-contrast text elements" for a single step.
        # querySelector() would silently measure whichever one it matches
        # first, misattributing the finding to an arbitrary element. Fall
        # back to the tool picking one real, specific sample instead of
        # measuring an ambiguous target.
        logger.warning("Ignoring compound contrast selector %r - not a single element", selector)
        selector = None
    if selector:
        measured = await contrast_tool.check_selector_contrast(page, selector, level=conformance_level or "AA")
        if measured is None:
            return StepResultSchema(
                status="needs_review",
                confidence=0.3,
                evidence={"selector": selector},
                reasoning="Could not locate the targeted element to measure contrast against.",
            )
    else:
        measured = _worst_contrast_sample(snapshot, conformance_level or "AA")
        if measured is None:
            return StepResultSchema(
                status="needs_review",
                confidence=0.2,
                evidence={},
                reasoning="No text/background color samples were available on this page to evaluate contrast.",
            )

    status = "pass" if measured["passes"] else "fail"
    return StepResultSchema(
        status=status,
        confidence=1.0,
        evidence=measured,
        reasoning=f"Measured contrast ratio {measured['ratio']} against a required {measured['required_ratio']}:1 "
        f"({'large' if measured['is_large_text'] else 'normal'} text).",
    )


def _worst_contrast_sample(snapshot: PageSnapshot, level: str) -> dict | None:
    worst: dict | None = None
    for sample in snapshot.contrast_samples:
        evaluated = contrast_tool.evaluate_contrast(
            foreground=sample.foreground,
            background=sample.background,
            font_size_px=sample.font_size_px,
            font_weight=sample.font_weight,
            level=level,
        )
        if evaluated["ratio"] is None:
            continue
        if worst is None or evaluated["ratio"] < worst["ratio"]:
            worst = {**evaluated, "selector": sample.selector, "text_preview": sample.text_preview, "html": sample.html}
    return worst


async def _run_keyboard_nav_step(page: Page) -> StepResultSchema:
    result = await keyboard_nav_tool.check_tab_order(page)

    if result.get("possible_interference"):
        # Focus left the page after only 1-2 stops with no trap/reordering
        # signal at all - more likely an overlay/animation still settling
        # (see keyboard_nav_tool.SUSPICIOUSLY_LOW_STOP_COUNT) than a genuine
        # "this page has almost no focusable elements" finding. Route to
        # manual review instead of reporting it as a confident result a
        # developer would otherwise chase as if it were real.
        return StepResultSchema(
            status="needs_review",
            confidence=0.2,
            evidence=result,
            reasoning=f"Only {result['stop_count']} tab stop(s) before focus left the page, with no trap or "
            "reordering signal - this looks like an overlay, animation, or lazy-mounted widget still settling "
            "rather than a real finding. Re-check manually with a screen reader before treating this as a defect.",
        )

    has_problems = bool(result["trap_detected"] or result["reordering_flags"] or result["invisible_focus_targets"])
    status = "fail" if has_problems else "pass"
    # A detected trap or an invisible focus target is unambiguous; the
    # upward-jump reordering heuristic is fuzzier, so confidence dips when
    # that's the only signal.
    confidence = 0.75 if (result["reordering_flags"] and not result["trap_detected"]) else 1.0
    return StepResultSchema(status=status, confidence=confidence, evidence=result, reasoning=_summarize_keyboard(result))


def _describe_stop(stop: dict) -> str:
    label = f" ({stop['label']})" if stop.get("label") else ""
    return f"<{stop['tag']}> {stop['selector']}{label}"


def _summarize_keyboard(result: dict) -> str:
    parts = [f"Simulated {result['stop_count']} tab stop(s)."]
    if result["trap_detected"] and result["stops"]:
        parts.append(f"A focus trap was detected at {_describe_stop(result['stops'][-1])} - focus stopped "
                     "advancing before reaching the end of the page.")
    if result["reordering_flags"]:
        examples = "; ".join(
            f"{_describe_stop(flag['from'])} -> {_describe_stop(flag['to'])}"
            for flag in result["reordering_flags"][:3]
        )
        parts.append(f"{len(result['reordering_flags'])} stop(s) suggest tab order does not follow visual order: "
                     f"{examples}.")
    if result["invisible_focus_targets"]:
        examples = "; ".join(_describe_stop(stop) for stop in result["invisible_focus_targets"][:3])
        parts.append(f"{len(result['invisible_focus_targets'])} focus stop(s) landed on a non-visible element: "
                     f"{examples}.")
    if len(parts) == 1:
        parts.append("No issues detected.")
    return " ".join(parts)


async def _run_screenshot_step(page: Page, target: dict, *, run_id: int, step_order: int) -> StepResultSchema:
    selector = target.get("selector")
    name = f"step_{step_order}"
    if selector:
        path = await screenshot_tool.capture_element(page, run_id, selector, name)
    else:
        path = await screenshot_tool.capture_full_page(page, run_id, name)

    if path:
        return StepResultSchema(
            status="pass", confidence=1.0, evidence={"screenshot_path": path}, reasoning="Captured visual evidence."
        )
    return StepResultSchema(
        status="needs_review", confidence=0.2, evidence={"selector": selector}, reasoning="Screenshot capture failed."
    )


# ── LLM judgment dispatch ────────────────────────────────────────────────

async def _execute_judgment_step(
    step: PlanStep, snapshot: PageSnapshot, conformance_level: str, *, is_followup: bool = False
) -> StepResultSchema:
    target = step.target_element or {}
    question = judgment_prompts.build_question(
        judgment_kind=target.get("judgment_kind"), wcag_criterion=step.wcag_criterion, target_element=target
    )
    if is_followup:
        question = (
            "This is a follow-up double-check: an earlier assessment of this exact question came back with low "
            f"confidence. Look carefully at the evidence and give your most confident assessment. {question}"
        )

    target_html = target.get("html") or target.get("context") or ""
    page_context = f"Page: {snapshot.title or snapshot.url} ({snapshot.url})"

    system_prompt = judgment_prompts.build_judgment_system_prompt(conformance_level)
    user_message = judgment_prompts.build_judgment_user_message(
        wcag_criterion=step.wcag_criterion, question=question, target_html=target_html, page_context=page_context
    )

    data = await llm_client.complete_structured(
        model=settings.AI_MODEL_JUDGMENT,
        system_prompt=system_prompt,
        user_message=user_message,
        schema=_STEP_RESULT_SCHEMA,
        # Generous ceiling even though the visible answer is short - Gemini's
        # internal "thinking" tokens draw from this same budget, and a tight
        # cap here risks truncating the JSON mid-string (see llm_client
        # docstring). AI_JUDGMENT_THINKING_BUDGET keeps the thinking itself
        # small/fast per step, matching the spec's "small, focused prompts".
        max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        thinking_budget=settings.AI_JUDGMENT_THINKING_BUDGET,
    )
    return StepResultSchema.model_validate(data)
