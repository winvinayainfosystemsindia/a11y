"""Pydantic DTOs for the crawler feature."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


class CrawlStartRequest(BaseModel):
    max_depth: int = Field(default=settings.CRAWLER_DEFAULT_MAX_DEPTH, ge=0, le=10)
    max_pages: int = Field(default=settings.CRAWLER_DEFAULT_MAX_PAGES, ge=1, le=2000)
    respect_robots: bool = Field(
        default=True,
        description="Set to false to override robots.txt Disallow rules for sites you own.",
    )


class CrawlStartResponse(BaseModel):
    project_id: int
    status: str
    message: str


class CrawlStatusResponse(BaseModel):
    project_id: int
    status: str
    page_count: int
    last_crawled_at: datetime | None = None
    error: str | None = None


class PageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    page_title: str | None = None
    status_code: int | None = None
    discovered_at: datetime
