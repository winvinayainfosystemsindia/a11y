"""
Read/write interface to the agent's persistent "brain" (ai_memory).

This is the only module inside app/ai/ that may cause a database write for
learned patterns, and even it never touches SQLAlchemy directly - every
call is delegated to app/repositories/ai_memory_repository.py, which is the
single place ai_memory rows are actually inserted/updated. The LLM never
gets a DB-writing tool; LEARN produces a list of `Lesson` objects (plain
data) and agent.py hands each one to `record_lesson` here.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.memory import embeddings
from app.ai.schemas import Lesson
from app.config import settings
from app.models.ai_memory import AIMemory
from app.repositories import ai_memory_repository

# How much a single confirmation/contradiction moves confidence_weight.
# Small and symmetric, so a pattern needs to be repeatedly right (or wrong)
# before the planner leans on it heavily - one noisy run can't flip it.
CONFIDENCE_STEP = 0.1
DEFAULT_NEW_PATTERN_CONFIDENCE = 0.5

_ACTION_TO_REPO_ACTION = {
    "confirm": "confirmed",
    "contradict": "contradicted",
}


def similarity_search(
    db: Session,
    query_text: str,
    *,
    page_type_signature: str | None = None,
    wcag_rule_id: str | None = None,
    top_n: int | None = None,
    min_similarity: float | None = None,
) -> list[tuple[AIMemory, float]]:
    vector = embeddings.embed_text(query_text)
    return ai_memory_repository.similarity_search(
        db,
        vector,
        page_type_signature=page_type_signature,
        wcag_rule_id=wcag_rule_id,
        top_n=top_n or settings.AI_MEMORY_TOP_N,
        min_similarity=min_similarity if min_similarity is not None else settings.AI_MEMORY_MIN_SIMILARITY,
    )


def patterns_for_page_type(db: Session, page_type_signature: str, *, limit: int = 10) -> list[AIMemory]:
    return ai_memory_repository.list_by_page_type(db, page_type_signature, limit=limit)


def get_exact(db: Session, page_type_signature: str, wcag_rule_id: str) -> AIMemory | None:
    return ai_memory_repository.get_by_signature_and_rule(db, page_type_signature, wcag_rule_id)


def record_lesson(db: Session, lesson: Lesson, *, audit_run_id: int) -> AIMemory:
    """Apply one Lesson produced by the Reflect/Learn stage.

    - action == "new": create a pattern row if one doesn't already exist for
      this (page_type_signature, wcag_rule_id) pair; if one does (the LLM
      proposed "new" for something already tracked), fall through to a
      confirmation instead of hitting the unique constraint.
    - action == "confirm"/"contradict": nudge an existing pattern's
      confidence up/down. If no matching row exists yet (the LLM referenced
      a pattern that was never actually stored), create it instead - the
      run still observed something worth remembering.

    Every branch ends in exactly one repository call, so exactly one
    AIMemoryUpdate row is written per Lesson - the audit trail this whole
    module exists for.
    """
    existing = ai_memory_repository.get_by_signature_and_rule(db, lesson.page_type_signature, lesson.wcag_rule_id)

    if existing is None:
        pattern_text = embeddings.build_pattern_text(
            lesson.page_type_signature, lesson.wcag_rule_id, lesson.pattern_description
        )
        vector = embeddings.embed_text(pattern_text)
        return ai_memory_repository.create_memory(
            db,
            page_type_signature=lesson.page_type_signature,
            wcag_rule_id=lesson.wcag_rule_id,
            pattern_description=lesson.pattern_description,
            outcome_pattern=lesson.outcome_pattern,
            confidence_weight=DEFAULT_NEW_PATTERN_CONFIDENCE,
            embedding=vector,
            audit_run_id=audit_run_id,
            reason=lesson.reason,
        )

    repo_action = _ACTION_TO_REPO_ACTION.get(lesson.action, "confirmed")
    delta = CONFIDENCE_STEP if repo_action == "confirmed" else -CONFIDENCE_STEP
    new_confidence = existing.confidence_weight + delta

    return ai_memory_repository.apply_update(
        db,
        existing.id,
        action=repo_action,
        reason=lesson.reason,
        new_confidence=new_confidence,
        audit_run_id=audit_run_id,
        outcome_pattern=lesson.outcome_pattern,
    )
