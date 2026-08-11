"""
Append-only audit trail for every write to ai_memory. LEARN never mutates a
memory row without recording why here - this is what makes the brain's
evolution inspectable instead of a black box.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

MEMORY_ACTION_CREATED = "created"
MEMORY_ACTION_CONFIRMED = "confirmed"
MEMORY_ACTION_CONTRADICTED = "contradicted"
MEMORY_ACTION_DECAYED = "decayed"


class AIMemoryUpdate(Base):
    __tablename__ = "ai_memory_updates"

    id: Mapped[int] = mapped_column(primary_key=True)
    ai_memory_id: Mapped[int] = mapped_column(ForeignKey("ai_memory.id", ondelete="CASCADE"), nullable=False)
    audit_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_runs.id", ondelete="SET NULL"), nullable=True
    )

    action: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_before: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_after: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
