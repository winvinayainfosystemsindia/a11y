"""DB access for refresh tokens."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.refresh_token import RefreshToken


def create_refresh_token(db: Session, *, user_id: int, token_hash: str, expires_at: datetime) -> RefreshToken:
    record = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_by_hash(db: Session, token_hash: str) -> RefreshToken | None:
    stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    return db.execute(stmt).scalar_one_or_none()


def revoke(db: Session, record: RefreshToken) -> None:
    record.revoked = True
    db.add(record)
    db.commit()


def is_valid(record: RefreshToken | None) -> bool:
    if record is None or record.revoked:
        return False
    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)
