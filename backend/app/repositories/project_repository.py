"""DB access for projects."""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.project import Project


def create_project(db: Session, *, user_id: int, name: str, base_url: str) -> Project:
    project = Project(user_id=user_id, name=name, base_url=base_url)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_for_user(db: Session, user_id: int) -> list[Project]:
    stmt = select(Project).where(Project.user_id == user_id).order_by(Project.created_at.desc())
    return list(db.execute(stmt).scalars().all())


def get_by_id(db: Session, project_id: int) -> Project | None:
    return db.get(Project, project_id)


def get_owned_by_user(db: Session, project_id: int, user_id: int) -> Project | None:
    stmt = select(Project).where(Project.id == project_id, Project.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def set_crawl_status(
    db: Session,
    project_id: int,
    *,
    status: str,
    error: str | None = None,
    last_crawled_at: datetime | None = None,
) -> None:
    project = db.get(Project, project_id)
    if project is None:
        return
    project.crawl_status = status
    project.crawl_error = error
    if last_crawled_at is not None:
        project.last_crawled_at = last_crawled_at
    db.add(project)
    db.commit()
