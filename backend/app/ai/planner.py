"""
PLAN stage: turns a PageSnapshot (with its attached MemoryContext) into a
structured AuditPlan via one scoped LLM call using Gemini structured
output, then validates it against the AuditPlan schema before anything
downstream sees it. Prioritizes checks memory says are common failure
points for this page type, without skipping any mandatory WCAG criterion.
"""
from __future__ import annotations

import logging

from app.ai import llm_client
from app.ai.prompts import planner_prompts
from app.ai.schemas import AuditPlan, PageSnapshot, PlanStepSchema
from app.config import settings
from app.utils.wcag_criteria import (
    ELEMENT_TYPES,
    axe_rules_for_criterion,
    criteria_for_level,
    criterion_name,
    level_for_criterion,
)

_ELEMENT_TYPES_SET = set(ELEMENT_TYPES)

logger = logging.getLogger(__name__)

_AUDIT_PLAN_SCHEMA = llm_client.build_structured_schema(AuditPlan)

# The tool names a step's `tool_name` field is allowed to hold - see
# _normalize_step_methods.
_KNOWN_TOOL_NAMES = {"axe", "contrast", "keyboard_nav", "screenshot"}


async def build_plan(snapshot: PageSnapshot, conformance_level: str) -> AuditPlan:
    system_prompt = planner_prompts.build_planner_system_prompt(conformance_level)
    user_message = planner_prompts.build_planner_user_message(snapshot, snapshot.memory_context)

    raw = await llm_client.complete_structured(
        model=settings.AI_MODEL_PLANNER,
        system_prompt=system_prompt,
        user_message=user_message,
        schema=_AUDIT_PLAN_SCHEMA,
        max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        thinking_budget=settings.AI_PLANNING_THINKING_BUDGET,
    )
    _normalize_step_methods(raw)
    plan = AuditPlan.model_validate(raw)
    _harden_step_facts(plan)
    _harden_element_types(plan)
    _harden_axe_rule_ids(plan)
    _ensure_mandatory_coverage(plan, conformance_level)
    plan.steps.sort(key=lambda step: step.priority)
    return plan


def _normalize_step_methods(raw: dict) -> None:
    """Repairs a specific drift seen live from a fallback model (Groq's
    json_object mode isn't a truly schema-constrained decode like Gemini's
    responseSchema, so it isn't structurally prevented from doing this): the
    model puts the specific tool's name (e.g. "contrast") directly into
    `method` instead of the literal "tool", leaving `method` failing
    Pydantic's tool|llm validation. Runs on the raw dict, before
    AuditPlan.model_validate, since that's where the mistake would otherwise
    raise before this function ever gets a typed step to fix."""
    for step in raw.get("steps") or []:
        if not isinstance(step, dict):
            continue
        method = step.get("method")
        if method in _KNOWN_TOOL_NAMES:
            logger.info("Correcting plan step: model put tool name %r in 'method' - setting method='tool'", method)
            step["tool_name"] = method
            step["method"] = "tool"


def _harden_step_facts(plan: AuditPlan) -> None:
    """WCAG level is a fixed fact per criterion, not a judgment call - never
    trust the LLM's `level` field when the criterion table already knows the
    real answer. Guards against a step correctly targeting e.g. 1.4.3 but
    mislabeling it level "A" (it's AA), which would otherwise corrupt the
    conformance-level breakdown in the final report."""
    for step in plan.steps:
        correct_level = level_for_criterion(step.wcag_criterion)
        if step.level != correct_level:
            logger.info(
                "Correcting plan step level for %s: model said %r, WCAG table says %r",
                step.wcag_criterion, step.level, correct_level,
            )
            step.level = correct_level  # type: ignore[assignment]


def _harden_element_types(plan: AuditPlan) -> None:
    """element_type is a plain str field, not a schema-enforced enum (see
    PlanStepSchema.element_type) - structured-output decoding doesn't
    guarantee the model picked one of the closed taxonomy values, so repair
    any drift here the same way _harden_step_facts repairs `level`, rather
    than letting an off-taxonomy string reach the Test Case sheet."""
    for step in plan.steps:
        if step.element_type not in _ELEMENT_TYPES_SET:
            logger.info(
                "Correcting plan step element_type for %s: model said %r, not in taxonomy - defaulting to "
                "'General Page'", step.wcag_criterion, step.element_type,
            )
            step.element_type = "General Page"


def _harden_axe_rule_ids(plan: AuditPlan) -> None:
    """Which axe-core rule(s) are relevant to a criterion is a fixed fact
    (WCAG_TO_AXE_RULES), not something worth trusting the LLM's
    target_element.axe_rule_ids guess unconditionally - the model can leave
    it unset, or name a rule that doesn't actually test this criterion. This
    is the deterministic backstop that prevents an axe-tagged step from ever
    running an unscoped axe pass and having an unrelated violation (e.g.
    color-contrast) stamped onto its report row.

    - If the criterion has no axe rule at all, the step can't be a
      deterministic axe check - demote it to an LLM judgment step.
    - Otherwise, replace target_element.axe_rule_ids with the known-correct
      rule set for this criterion (dropping any off-mapping ids the model
      invented), so downstream axe scoping and violation matching are both
      grounded in the same table.
    """
    for step in plan.steps:
        if step.method != "tool" or step.tool_name != "axe":
            continue
        expected = axe_rules_for_criterion(step.wcag_criterion)
        if not expected:
            logger.info(
                "Demoting plan step for %s from tool='axe' to method='llm': no axe-core rule "
                "reliably tests this criterion, so it cannot be a deterministic axe check.",
                step.wcag_criterion,
            )
            step.method = "llm"  # type: ignore[assignment]
            step.tool_name = None
            continue

        current = step.target_element.get("axe_rule_ids") or []
        if not set(current) & set(expected):
            logger.info(
                "Correcting axe_rule_ids for %s: model said %r, WCAG table says %r",
                step.wcag_criterion, current, expected,
            )
            step.target_element["axe_rule_ids"] = expected
        else:
            # Keep only the ids that actually test this criterion - drop any
            # unrelated ones the model tacked on alongside a correct guess.
            step.target_element["axe_rule_ids"] = [r for r in current if r in expected]


def _ensure_mandatory_coverage(plan: AuditPlan, conformance_level: str) -> None:
    """Defensive backstop, independent of prompt instructions: if the
    generated plan is missing a mandatory criterion, append a low-priority
    judgment step for it rather than silently letting a plan through that
    skips something the audit was required to cover."""
    covered = {step.wcag_criterion for step in plan.steps}
    mandatory = criteria_for_level(conformance_level)
    for sc_id, name in mandatory:
        if sc_id in covered:
            continue
        logger.warning("Backfilling mandatory criterion %s missing from generated plan", sc_id)
        plan.steps.append(
            PlanStepSchema(
                title=f"{name} ({sc_id}) - general review",
                wcag_criterion=sc_id,
                level=level_for_criterion(sc_id),  # type: ignore[arg-type]
                method="llm",
                target_element={
                    "description": f"General review of {criterion_name(sc_id)} ({sc_id}) - the generated plan did "
                    "not cover it; this step was backfilled automatically."
                },
                priority=3,
                reasoning="Backfilled: mandatory criterion missing from the generated plan.",
            )
        )
