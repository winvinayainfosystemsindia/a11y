"""HTTP layer for starting crawls and reading crawl results, scoped under
a project the current user owns."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers import crawl_controller, project_controller
from app.controllers.errors import NotFoundError
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.project import CRAWL_STATUS_RUNNING
from app.models.user import User
from app.schemas.crawl import CrawlStartRequest, CrawlStartResponse, CrawlStatusResponse, PageOut

router = APIRouter(prefix="/api/projects/{project_id}", tags=["crawl"])


def _get_owned_project(db: Session, project_id: int, current_user: User):
    try:
        return project_controller.get_project_or_raise(db, project_id, current_user.id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/crawl", response_model=CrawlStartResponse, status_code=status.HTTP_202_ACCEPTED)
def start_crawl(
    project_id: int,
    payload: CrawlStartRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrawlStartResponse:
    project = _get_owned_project(db, project_id, current_user)

    if project.crawl_status == CRAWL_STATUS_RUNNING:
        return CrawlStartResponse(
            project_id=project.id, status=CRAWL_STATUS_RUNNING, message="A crawl is already in progress"
        )

    crawl_controller.begin_crawl(db, project)
    background_tasks.add_task(
        crawl_controller.run_crawl_job,
        project.id,
        project.base_url,
        payload.max_depth,
        payload.max_pages,
        payload.respect_robots,
    )
    return CrawlStartResponse(
        project_id=project.id, status=CRAWL_STATUS_RUNNING, message="Crawl started"
    )


@router.get("/crawl/status", response_model=CrawlStatusResponse)
def crawl_status(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CrawlStatusResponse:
    project = _get_owned_project(db, project_id, current_user)
    status_value, page_count, error = crawl_controller.get_crawl_status(db, project)
    return CrawlStatusResponse(
        project_id=project.id,
        status=status_value,
        page_count=page_count,
        last_crawled_at=project.last_crawled_at,
        error=error,
    )


@router.get("/pages", response_model=list[PageOut])
def list_pages(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PageOut]:
    project = _get_owned_project(db, project_id, current_user)
    pages = crawl_controller.list_pages(db, project)
    return [PageOut.model_validate(p) for p in pages]
