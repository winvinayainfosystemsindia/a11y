"""
Business logic for signup / login / refresh / logout. No HTTP concerns and
no raw DB queries here - all persistence goes through repositories.
"""
from sqlalchemy.orm import Session

from app.controllers.errors import DuplicateEmailError, InvalidCredentialsError, InvalidRefreshTokenError
from app.models.user import User
from app.repositories import token_repository, user_repository
from app.schemas.auth import TokenResponse
from app.schemas.user import UserCreate
from app.services import security_service


def signup(db: Session, payload: UserCreate) -> User:
    existing = user_repository.get_by_email(db, payload.email)
    if existing is not None:
        raise DuplicateEmailError()

    hashed = security_service.hash_password(payload.password)
    return user_repository.create_user(
        db, full_name=payload.full_name, email=payload.email, hashed_password=hashed
    )


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access_token = security_service.create_access_token(subject=str(user.id))
    raw_refresh_token = security_service.generate_refresh_token()
    token_repository.create_refresh_token(
        db,
        user_id=user.id,
        token_hash=security_service.hash_refresh_token(raw_refresh_token),
        expires_at=security_service.refresh_token_expiry(),
    )
    return TokenResponse(access_token=access_token, refresh_token=raw_refresh_token)


def login(db: Session, email: str, password: str) -> TokenResponse:
    user = user_repository.get_by_email(db, email)
    if user is None or not user.is_active or not security_service.verify_password(password, user.hashed_password):
        raise InvalidCredentialsError()
    return _issue_tokens(db, user)


def refresh_access_token(db: Session, raw_refresh_token: str) -> TokenResponse:
    """
    Validates the refresh token and rotates it: the old one is revoked and a
    brand new access + refresh token pair is issued. Rotation limits the
    damage if a refresh token is ever leaked.
    """
    token_hash = security_service.hash_refresh_token(raw_refresh_token)
    record = token_repository.get_by_hash(db, token_hash)
    if not token_repository.is_valid(record):
        raise InvalidRefreshTokenError()

    user = user_repository.get_by_id(db, record.user_id)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError()

    token_repository.revoke(db, record)
    return _issue_tokens(db, user)


def logout(db: Session, raw_refresh_token: str) -> None:
    token_hash = security_service.hash_refresh_token(raw_refresh_token)
    record = token_repository.get_by_hash(db, token_hash)
    if record is not None and not record.revoked:
        token_repository.revoke(db, record)
