"""
DB access for the persistent "brain" (ai_memory) and its audit trail
(ai_memory_updates). This is the only module that writes ai_memory rows -
app/ai/memory/memory_store.py calls into here; the LLM itself never touches
the database directly (see app/ai/memory/memory_store.py docstring).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session

from app.models.ai_memory import AIMemory
from app.models.ai_memory_update import AIMemoryUpdate

logger = logging.getLogger(__name__)

_UNDEFINED_TABLE = "42P01"  # Postgres SQLSTATE for "relation does not exist"
_warned_table_missing = False


def _is_table_missing(db: Session, exc: ProgrammingError) -> bool:
    """True (after rolling back the aborted transaction) if `exc` is Postgres
    complaining that ai_memory/ai_memory_updates doesn't exist yet - i.e. the
    pgvector-dependent migration (c4b8e1f2a9d0) hasn't been applied. Callers
    treat that as "AI memory feature not set up" rather than a hard failure,
    so one audit run's missing table doesn't take down the whole loop."""
    global _warned_table_missing
    orig = getattr(exc, "orig", None)
    if getattr(orig, "pgcode", None) != _UNDEFINED_TABLE:
        return False
    db.rollback()
    if not _warned_table_missing:
        logger.warning(
            "ai_memory table not found - AI memory/learning is disabled until pgvector is installed "
            "and 'alembic upgrade head' is run (see alembic/versions/c4b8e1f2a9d0_ai_memory_vector.py)."
        )
        _warned_table_missing = True
    return True


def similarity_search(
    db: Session,
    embedding: list[float],
    *,
    page_type_signature: str | None = None,
    wcag_rule_id: str | None = None,
    top_n: int = 5,
    min_similarity: float = 0.0,
) -> list[tuple[AIMemory, float]]:
    """Top-N memories by cosine similarity to `embedding`, optionally scoped
    to an exact page-type and/or rule match. Similarity = 1 - cosine_distance
    (pgvector's `<=>` operator), so higher is more relevant."""
    distance = AIMemory.embedding.cosine_distance(embedding)
    stmt = select(AIMemory, distance.label("distance"))
    if page_type_signature is not None:
        stmt = stmt.where(AIMemory.page_type_signature == page_type_signature)
    if wcag_rule_id is not None:
        stmt = stmt.where(AIMemory.wcag_rule_id == wcag_rule_id)
    stmt = stmt.order_by(distance.asc()).limit(top_n)

    try:
        rows = db.execute(stmt).all()
    except ProgrammingError as exc:
        if not _is_table_missing(db, exc):
            raise
        return []

    results: list[tuple[AIMemory, float]] = []
    for memory, distance_value in rows:
        similarity = 1.0 - float(distance_value)
        if similarity >= min_similarity:
            results.append((memory, similarity))
    return results


def list_by_page_type(db: Session, page_type_signature: str, *, limit: int = 10) -> list[AIMemory]:
    """Every known pattern for an exact page-type match, regardless of
    similarity score - used for rule-specific pattern lookups (spec 1c)
    where an exact structural match matters more than semantic closeness."""
    stmt = (
        select(AIMemory)
        .where(AIMemory.page_type_signature == page_type_signature)
        .order_by(AIMemory.confidence_weight.desc(), AIMemory.times_seen.desc())
        .limit(limit)
    )
    try:
        return list(db.execute(stmt).scalars().all())
    except ProgrammingError as exc:
        if not _is_table_missing(db, exc):
            raise
        return []


def get_by_signature_and_rule(db: Session, page_type_signature: str, wcag_rule_id: str) -> AIMemory | None:
    stmt = select(AIMemory).where(
        AIMemory.page_type_signature == page_type_signature,
        AIMemory.wcag_rule_id == wcag_rule_id,
    )
    try:
        return db.execute(stmt).scalar_one_or_none()
    except ProgrammingError as exc:
        if not _is_table_missing(db, exc):
            raise
        return None


def create_memory(
    db: Session,
    *,
    page_type_signature: str,
    wcag_rule_id: str,
    pattern_description: str,
    outcome_pattern: str,
    confidence_weight: float,
    embedding: list[float],
    audit_run_id: int | None,
    reason: str,
) -> AIMemory:
    memory = AIMemory(
        page_type_signature=page_type_signature,
        wcag_rule_id=wcag_rule_id,
        pattern_description=pattern_description,
        outcome_pattern=outcome_pattern,
        confidence_weight=confidence_weight,
        embedding=embedding,
        times_seen=1,
    )
    db.add(memory)
    db.flush()  # assign memory.id before logging the update row

    db.add(
        AIMemoryUpdate(
            ai_memory_id=memory.id,
            audit_run_id=audit_run_id,
            action="created",
            reason=reason,
            confidence_before=0.0,
            confidence_after=confidence_weight,
        )
    )
    db.commit()
    db.refresh(memory)
    return memory


def apply_update(
    db: Session,
    memory_id: int,
    *,
    action: str,
    reason: str,
    new_confidence: float,
    audit_run_id: int | None,
    outcome_pattern: str | None = None,
) -> AIMemory | None:
    """Mutate a memory row and log why, in the same transaction, so the two
    can never drift - a confidence change with no matching AIMemoryUpdate
    row should never be possible to produce with this function."""
    memory = db.get(AIMemory, memory_id)
    if memory is None:
        return None

    confidence_before = memory.confidence_weight
    new_confidence = max(0.0, min(1.0, new_confidence))

    db.add(
        AIMemoryUpdate(
            ai_memory_id=memory.id,
            audit_run_id=audit_run_id,
            action=action,
            reason=reason,
            confidence_before=confidence_before,
            confidence_after=new_confidence,
        )
    )

    memory.confidence_weight = new_confidence
    memory.times_seen += 1
    now = datetime.now(timezone.utc)
    if action == "confirmed":
        memory.last_confirmed_at = now
    elif action == "contradicted":
        memory.last_contradicted_at = now
    if outcome_pattern is not None:
        memory.outcome_pattern = outcome_pattern

    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


def list_updates_for_memory(db: Session, memory_id: int) -> list[AIMemoryUpdate]:
    stmt = (
        select(AIMemoryUpdate)
        .where(AIMemoryUpdate.ai_memory_id == memory_id)
        .order_by(AIMemoryUpdate.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
