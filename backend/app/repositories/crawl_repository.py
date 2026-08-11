"""DB access for crawled pages."""
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.crawled_page import CrawledPage
from app.services.crawler_service import PageResult


def replace_pages_for_project(db: Session, project_id: int, pages: list[PageResult]) -> None:
    """
    Atomically swap the stored page set for a project with the results of a
    fresh crawl, so re-crawling a site never leaves stale/removed pages
    behind while still deduplicating by normalized URL.
    """
    db.execute(delete(CrawledPage).where(CrawledPage.project_id == project_id))
    seen: set[str] = set()
    for page in pages:
        if page.url in seen:
            continue
        seen.add(page.url)
        db.add(
            CrawledPage(
                project_id=project_id,
                url=page.url,
                page_title=page.title,
                status_code=page.status_code,
            )
        )
    db.commit()


def list_pages_for_project(db: Session, project_id: int) -> list[CrawledPage]:
    stmt = (
        select(CrawledPage)
        .where(CrawledPage.project_id == project_id)
        .order_by(CrawledPage.url.asc())
    )
    return list(db.execute(stmt).scalars().all())


def count_pages_for_project(db: Session, project_id: int) -> int:
    return len(list_pages_for_project(db, project_id))
