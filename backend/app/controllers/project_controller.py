"""Business logic for creating and listing audit projects."""
from sqlalchemy.orm import Session

from app.controllers.errors import NotFoundError
from app.models.project import Project
from app.repositories import project_repository
from app.schemas.project import ProjectCreate


def create_project(db: Session, user_id: int, payload: ProjectCreate) -> Project:
    return project_repository.create_project(
        db, user_id=user_id, name=payload.name, base_url=payload.base_url
    )


def list_projects(db: Session, user_id: int) -> list[Project]:
    return project_repository.list_for_user(db, user_id)


def get_project_or_raise(db: Session, project_id: int, user_id: int) -> Project:
    project = project_repository.get_owned_by_user(db, project_id, user_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project
