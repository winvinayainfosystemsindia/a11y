"""
REFLECT stage: reviews the full set of StepResults after EXECUTE finishes.
One scoped, structured LLM call flags low-confidence findings, cross-checks
results against the memory consulted during planning for contradictions,
notes near-duplicate findings worth merging, and proposes the Lesson list
LEARN will persist. A deterministic backstop (independent of the prompt)
guarantees every genuinely low-confidence result is surfaced, never hidden.
"""
from __future__ import annotations

import logging

from app.ai import llm_client
from app.ai.prompts import reflection_prompts
from app.ai.schemas import PageSnapshot, Reflection
from app.config import settings
from app.models.plan_step import PlanStep

logger = logging.getLogger(__name__)

_REFLECTION_SCHEMA = llm_client.build_structured_schema(Reflection)


async def reflect(plan_steps: list[PlanStep], snapshot: PageSnapshot, conformance_level: str) -> Reflection:
    payload = _serialize_steps(plan_steps)

    system_prompt = reflection_prompts.build_reflection_system_prompt(
        conformance_level, settings.AI_LOW_CONFIDENCE_THRESHOLD
    )
    user_message = reflection_prompts.build_reflection_user_message(
        page_title=snapshot.title,
        page_url=snapshot.url,
        page_type_signature=snapshot.page_type_signature,
        plan_steps_with_results=payload,
        memory=snapshot.memory_context,
    )

    raw = await llm_client.complete_structured(
        model=settings.AI_MODEL_REFLECTION,
        system_prompt=system_prompt,
        user_message=user_message,
        schema=_REFLECTION_SCHEMA,
        max_tokens=settings.AI_MAX_OUTPUT_TOKENS,
        thinking_budget=settings.AI_PLANNING_THINKING_BUDGET,
    )
    reflection = Reflection.model_validate(raw)
    _ensure_low_confidence_surfaced(reflection, plan_steps)
    return reflection


def _serialize_steps(plan_steps: list[PlanStep]) -> list[dict]:
    serialized: list[dict] = []
    for step in plan_steps:
        latest = step.results[-1] if step.results else None
        serialized.append(
            {
                "plan_step_id": step.id,
                "title": step.title,
                "wcag_criterion": step.wcag_criterion,
                "level": step.level,
                "method": step.method,
                "tool_name": step.tool_name,
                "priority": step.priority,
                "status": latest.status if latest else "not_run",
                "confidence": latest.confidence if latest else None,
                "reasoning": latest.reasoning if latest else None,
                "had_followup": len(step.results) > 1,
            }
        )
    return serialized


def _ensure_low_confidence_surfaced(reflection: Reflection, plan_steps: list[PlanStep]) -> None:
    """Never let a genuinely low-confidence result go unflagged just
    because the reflection call missed it - this must always reach the
    user, not be silently discarded (spec requirement, not a suggestion)."""
    flagged = set(reflection.low_confidence_plan_step_ids)
    for step in plan_steps:
        if not step.results:
            continue
        latest = step.results[-1]
        if latest.confidence < settings.AI_LOW_CONFIDENCE_THRESHOLD and step.id not in flagged:
            logger.info("Backstop-flagging low-confidence plan step %s (confidence=%.2f)", step.id, latest.confidence)
            reflection.low_confidence_plan_step_ids.append(step.id)
