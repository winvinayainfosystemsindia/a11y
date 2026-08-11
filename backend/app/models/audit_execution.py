"""
One row per "Audit Selected Pages" trigger from the UI. Groups the N
per-page AuditRuns created for that trigger under a single id, so the
frontend can show one execution with N pages' progress instead of N
independent executions/reports. Aggregate status/progress is computed
on the fly from the child AuditRuns (see audit_controller.get_execution_status)
rather than stored here, so N concurrent background jobs never need to
write to this shared row.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AuditExecution(Base):
    __tablename__ = "audit_executions"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    conformance_level: Mapped[str] = mapped_column(String(4), default="AA", nullable=False)
    total_pages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    project: Mapped["Project"] = relationship("Project")
    runs: Mapped[list["AuditRun"]] = relationship(
        "AuditRun", back_populates="execution", order_by="AuditRun.id"
    )
