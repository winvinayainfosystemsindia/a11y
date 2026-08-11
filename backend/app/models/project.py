"""
A Project represents one site/app a user wants to audit for accessibility.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# Simple string status column (not a DB enum) so new statuses can be added
# without an Alembic migration for the enum type itself.
CRAWL_STATUS_IDLE = "idle"
CRAWL_STATUS_RUNNING = "running"
CRAWL_STATUS_COMPLETED = "completed"
CRAWL_STATUS_FAILED = "failed"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    crawl_status: Mapped[str] = mapped_column(String(20), default=CRAWL_STATUS_IDLE, nullable=False)
    crawl_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="projects")
    pages: Mapped[list["CrawledPage"]] = relationship(
        "CrawledPage", back_populates="project", cascade="all, delete-orphan"
    )
