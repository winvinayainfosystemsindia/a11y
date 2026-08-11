"""HTTP layer for the standalone WCAG Success Criteria Library reference sheet."""
from fastapi import APIRouter, Depends, Query

from app.controllers import wcag_controller
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.wcag import SuccessCriteriaListOut

router = APIRouter(prefix="/api/wcag", tags=["wcag"])


@router.get("/success-criteria", response_model=SuccessCriteriaListOut)
def list_success_criteria(
    level: str | None = Query(default=None, pattern="^(A|AA)$"),
    current_user: User = Depends(get_current_user),
) -> SuccessCriteriaListOut:
    return SuccessCriteriaListOut(items=wcag_controller.list_success_criteria(level))
