"""HTTP layer for the current user's profile."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.controllers import user_controller
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    profile = user_controller.get_profile(db, current_user)
    return UserOut.model_validate(profile)
