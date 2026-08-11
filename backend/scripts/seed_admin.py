"""
Idempotent dev/test seed: creates the default user from the
DEFAULT_ADMIN_* settings (see .env) if no user with that email exists yet.
Safe to run repeatedly - it skips creation if the account is already there.

Usage (from the backend/ directory, with the venv active):
    python -m scripts.seed_admin
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.repositories import user_repository  # noqa: E402
from app.services import security_service  # noqa: E402


def seed_default_admin() -> None:
    if not settings.DEFAULT_ADMIN_EMAIL or not settings.DEFAULT_ADMIN_PASSWORD:
        print("DEFAULT_ADMIN_EMAIL / DEFAULT_ADMIN_PASSWORD not set in .env - nothing to seed.")
        return

    db = SessionLocal()
    try:
        existing = user_repository.get_by_email(db, settings.DEFAULT_ADMIN_EMAIL)
        if existing is not None:
            print(f"User {settings.DEFAULT_ADMIN_EMAIL} already exists (id={existing.id}) - skipping.")
            return

        hashed_password = security_service.hash_password(settings.DEFAULT_ADMIN_PASSWORD)
        user = user_repository.create_user(
            db,
            full_name=settings.DEFAULT_ADMIN_FULL_NAME,
            email=settings.DEFAULT_ADMIN_EMAIL,
            hashed_password=hashed_password,
        )
        print(f"Created default user {user.email} (id={user.id}).")
    finally:
        db.close()


if __name__ == "__main__":
    seed_default_admin()
