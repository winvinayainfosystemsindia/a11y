"""
Business logic for starting crawls and reading crawl results. The actual
crawl runs in a background task (scheduled by the view) so the HTTP request
returns immediately with a "started" status instead of blocking.
"""
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.crawled_page import CrawledPage
from app.models.project import (
    CRAWL_STATUS_COMPLETED,
    CRAWL_STATUS_FAILED,
    CRAWL_STATUS_RUNNING,
    Project,
)
from app.repositories import crawl_repository, project_repository
from app.services import crawler_service
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def begin_crawl(db: Session, project: Project) -> None:
    """Marks the project as 'running'. Call before scheduling the background job."""
    project_repository.set_crawl_status(db, project.id, status=CRAWL_STATUS_RUNNING, error=None)


async def run_crawl_job(
    project_id: int, base_url: str, max_depth: int, max_pages: int, respect_robots: bool
) -> None:
    """
    The actual background job. Opens its own DB session because it runs
    after the original request's session has already been closed.
    """
    db = SessionLocal()
    try:
        pages = await crawler_service.crawl_site(
            base_url, max_depth=max_depth, max_pages=max_pages, respect_robots=respect_robots
        )
        crawl_repository.replace_pages_for_project(db, project_id, pages)
        project_repository.set_crawl_status(
            db, project_id, status=CRAWL_STATUS_COMPLETED, last_crawled_at=datetime.now(timezone.utc)
        )
    except Exception as exc:  # noqa: BLE001 - surface any crawl failure on the project
        logger.exception("Crawl failed for project %s", project_id)
        project_repository.set_crawl_status(db, project_id, status=CRAWL_STATUS_FAILED, error=str(exc)[:1024])
    finally:
        db.close()


def get_crawl_status(db: Session, project: Project) -> tuple[str, int, str | None]:
    page_count = crawl_repository.count_pages_for_project(db, project.id)
    return project.crawl_status, page_count, project.crawl_error


def list_pages(db: Session, project: Project) -> list[CrawledPage]:
    return crawl_repository.list_pages_for_project(db, project.id)
