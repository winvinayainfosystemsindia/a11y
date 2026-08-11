"""
RAG-style retrieval: called by PERCEIVE (via agent.py) before PLAN runs.
Pulls three kinds of prior knowledge and assembles them into a
MemoryContext:

  (a) past audits of this exact URL           -> audit_repository
  (b) structurally similar pages, by embedding -> memory_store.similarity_search
  (c) rule-specific patterns for this page type -> memory_store.patterns_for_page_type

The planner and executor both read the resulting MemoryContext; neither
queries ai_memory directly.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai.memory import embeddings, memory_store
from app.ai.schemas import MemoryContext
from app.config import settings
from app.repositories import audit_repository


def build_memory_context(
    db: Session,
    *,
    page_id: int,
    page_type_signature: str,
    page_type_description: str,
    current_run_id: int | None = None,
) -> MemoryContext:
    exact_url_history = [
        {
            "audit_run_id": run.id,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "reflection_summary": run.reflection_summary,
        }
        for run in audit_repository.list_recent_completed_runs_for_page(
            db, page_id, exclude_run_id=current_run_id, limit=3
        )
        if run.reflection_summary
    ]

    query_text = embeddings.build_pattern_text(page_type_signature, "*", page_type_description)
    similar = memory_store.similarity_search(
        db,
        query_text,
        top_n=settings.AI_MEMORY_TOP_N,
        min_similarity=settings.AI_MEMORY_MIN_SIMILARITY,
    )
    similar_page_findings = [
        {
            "page_type_signature": memory.page_type_signature,
            "wcag_rule_id": memory.wcag_rule_id,
            "pattern_description": memory.pattern_description,
            "outcome_pattern": memory.outcome_pattern,
            "confidence_weight": round(memory.confidence_weight, 3),
            "times_seen": memory.times_seen,
            "similarity": round(similarity, 3),
        }
        for memory, similarity in similar
    ]

    rule_specific_patterns = [
        {
            "wcag_rule_id": memory.wcag_rule_id,
            "pattern_description": memory.pattern_description,
            "outcome_pattern": memory.outcome_pattern,
            "confidence_weight": round(memory.confidence_weight, 3),
            "times_seen": memory.times_seen,
        }
        for memory in memory_store.patterns_for_page_type(db, page_type_signature, limit=10)
    ]

    return MemoryContext(
        exact_url_history=exact_url_history,
        similar_page_findings=similar_page_findings,
        rule_specific_patterns=rule_specific_patterns,
    )
