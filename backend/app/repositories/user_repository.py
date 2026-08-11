"""
DB access for users. This is the only layer allowed to build SQLAlchemy
queries against the User table.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get_by_id(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_email(db: Session, email: str) -> User | None:
    stmt = select(User).where(User.email == email.lower())
    return db.execute(stmt).scalar_one_or_none()


def create_user(db: Session, *, full_name: str, email: str, hashed_password: str) -> User:
    user = User(full_name=full_name, email=email.lower(), hashed_password=hashed_password)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
