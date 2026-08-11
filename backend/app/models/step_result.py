"""
Result of executing exactly one PlanStep. Written immediately when the step
finishes (pass, fail, or needs_review) - never batched until the end of the
run - so a crash mid-run doesn't lose completed work. A low-confidence result
may spawn one `follow_up_of_id` re-check step, never a full re-run.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

STEP_RESULT_PASS = "pass"
STEP_RESULT_FAIL = "fail"
STEP_RESULT_NEEDS_REVIEW = "needs_review"


class StepResult(Base):
    __tablename__ = "step_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_step_id: Mapped[int] = mapped_column(ForeignKey("plan_steps.id", ondelete="CASCADE"), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    # Structured evidence: matched DOM snippet(s), computed contrast ratio,
    # screenshot path, axe rule id, tab-order trace, etc. - whatever the
    # executing tool or LLM judgment call produced.
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_follow_up: Mapped[bool] = mapped_column(default=False, nullable=False)
    follow_up_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("step_results.id", ondelete="SET NULL"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    plan_step: Mapped["PlanStep"] = relationship("PlanStep", back_populates="results")
