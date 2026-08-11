"""
The audit agent's persistent "brain". Each row is one learned pattern - a
WCAG rule's typical outcome for a page-type signature (or a free-form
component pattern like "carousels on this site miss aria-roledescription").
retriever.py does cosine-similarity search over `embedding` (pgvector) plus
exact page_type_signature/wcag_rule_id matches to feed planner.py and
executor.py. Every change to a row is logged via AIMemoryUpdate - never
overwritten silently.
"""
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.config import settings
from app.database import Base

OUTCOME_USUALLY_FAILS = "usually_fails"
OUTCOME_USUALLY_PASSES = "usually_passes"
OUTCOME_MIXED = "mixed"


class AIMemory(Base):
    __tablename__ = "ai_memory"
    __table_args__ = (
        UniqueConstraint("page_type_signature", "wcag_rule_id", name="uq_ai_memory_signature_rule"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    # A short, stable descriptor of the kind of page this pattern applies to
    # (e.g. "login_form", "product_listing", "checkout", "generic"). Produced
    # by the PERCEIVE stage from page structure, not the raw URL.
    page_type_signature: Mapped[str] = mapped_column(String(128), nullable=False)
    wcag_rule_id: Mapped[str] = mapped_column(String(64), nullable=False)

    pattern_description: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_pattern: Mapped[str] = mapped_column(String(20), default=OUTCOME_MIXED, nullable=False)

    # 0..1 - how much the planner/executor should trust this pattern. Nudged
    # up on confirmation, down (and eventually pruned in spirit, never
    # deleted) on contradiction. See ai_memory_repository.apply_update.
    confidence_weight: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    times_seen: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    embedding: Mapped[list[float]] = mapped_column(Vector(settings.AI_EMBEDDING_DIMENSIONS), nullable=False)

    last_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_contradicted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
