"""Business logic for the current user's own profile."""
from sqlalchemy.orm import Session

from app.models.user import User


def get_profile(db: Session, current_user: User) -> User:
    # Placeholder for future profile-enrichment logic (Phase 1 just returns the user).
    return current_user
