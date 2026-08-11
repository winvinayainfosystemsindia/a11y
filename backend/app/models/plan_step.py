"""
One row per step of an AuditPlan produced by the PLAN stage. Written before
execution begins so a crash mid-run leaves a durable record of what was
planned, independent of what actually completed (see StepResult).
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

METHOD_TOOL = "tool"
METHOD_LLM = "llm"

PLAN_STEP_STATUS_PENDING = "pending"
PLAN_STEP_STATUS_RUNNING = "running"
PLAN_STEP_STATUS_PASSED = "passed"
PLAN_STEP_STATUS_FAILED = "failed"
PLAN_STEP_STATUS_NEEDS_REVIEW = "needs_review"
PLAN_STEP_STATUS_SKIPPED = "skipped"


class PlanStep(Base):
    __tablename__ = "plan_steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    audit_run_id: Mapped[int] = mapped_column(ForeignKey("audit_runs.id", ondelete="CASCADE"), nullable=False)

    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Short, human-readable test case name (e.g. "Submit button has an
    # accessible name") - distinct from `reasoning`, which explains *why*
    # the step exists. Authored by the LLM at PLAN time; this is what
    # populates the Test Case sheet's "Test Case Name" column.
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    wcag_criterion: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(4), default="AA", nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Free-form description of the element(s) this step targets (a CSS
    # selector, an axe rule id, "all <img> without alt", ...).
    target_element: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # Closed-taxonomy label (see app.utils.wcag_criteria.ELEMENT_TYPES) for the
    # "Element / Component Type on Page" column - distinct from target_element,
    # which is the free-form selector/description a tool or judgment call needs.
    element_type: Mapped[str] = mapped_column(String(80), default="General Page", nullable=False)

    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1 (highest) .. 5 (lowest)
    reasoning: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=PLAN_STEP_STATUS_PENDING, nullable=False)

    # Human QA override of the AI-derived pass/fail/needs_review verdict (see
    # StepResult.status) - null until a reviewer explicitly overrides it via
    # the PATCH endpoint, at which point it wins in audit_controller._build_test_cases.
    manual_status_override: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Defect lifecycle status (Open/In Progress/Fixed/Retest/Closed/Won't Fix) -
    # tracks remediation progress, independent of the pass/fail verdict above.
    # Only meaningful once the step's derived status isn't "pass".
    defect_status: Mapped[str] = mapped_column(String(20), default="Open", nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    audit_run: Mapped["AuditRun"] = relationship("AuditRun", back_populates="plan_steps")
    results: Mapped[list["StepResult"]] = relationship(
        "StepResult", back_populates="plan_step", cascade="all, delete-orphan", order_by="StepResult.created_at"
    )
