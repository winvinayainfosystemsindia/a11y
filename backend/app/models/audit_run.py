"""
One row per AI audit run of a single crawled page. Tracks the run through
the Perceive -> Plan -> Execute -> Reflect -> Learn loop; `status` is the
single source of truth the frontend polls to render live progress.
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Plain string status column (not a DB enum), matching the convention used by
# Project.crawl_status - new stages can be added without a migration.
AUDIT_STATUS_QUEUED = "queued"
AUDIT_STATUS_PERCEIVING = "perceiving"
AUDIT_STATUS_PLANNING = "planning"
AUDIT_STATUS_EXECUTING = "executing"
AUDIT_STATUS_REFLECTING = "reflecting"
AUDIT_STATUS_LEARNING = "learning"
AUDIT_STATUS_COMPLETED = "completed"
AUDIT_STATUS_FAILED = "failed"

TERMINAL_STATUSES = {AUDIT_STATUS_COMPLETED, AUDIT_STATUS_FAILED}


class AuditRun(Base):
    __tablename__ = "audit_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[int] = mapped_column(ForeignKey("crawled_pages.id", ondelete="CASCADE"), nullable=False)
    # Nullable so the single-page /pages/{page_id}/audit endpoint (no batch
    # grouping) keeps working unchanged. Batch-created runs always set this.
    execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("audit_executions.id", ondelete="CASCADE"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(20), default=AUDIT_STATUS_QUEUED, nullable=False)
    conformance_level: Mapped[str] = mapped_column(String(4), default="AA", nullable=False)

    # Compact structured snapshot of what PERCEIVE saw (title, landmarks,
    # forms, images, page-type signature, ...). Deliberately not the raw
    # HTML dump - that lives only transiently in memory during the run.
    perception: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Stage 4 (Reflect) output: contradictions, low-confidence flags, dedup
    # notes, and the narrative summary shown to the user.
    reflection_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    total_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project")
    page: Mapped["CrawledPage"] = relationship("CrawledPage")
    execution: Mapped["AuditExecution | None"] = relationship("AuditExecution", back_populates="runs")
    plan_steps: Mapped[list["PlanStep"]] = relationship(
        "PlanStep", back_populates="audit_run", cascade="all, delete-orphan", order_by="PlanStep.step_order"
    )
