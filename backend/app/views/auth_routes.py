"""HTTP layer for authentication. Translates controller domain errors into
HTTPExceptions and returns Pydantic schemas - never ORM models."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.controllers import auth_controller
from app.controllers.errors import DuplicateEmailError, InvalidCredentialsError, InvalidRefreshTokenError
from app.database import get_db
from app.schemas.auth import LoginRequest, LogoutRequest, MessageResponse, RefreshRequest, TokenResponse
from app.schemas.user import UserCreate, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> UserOut:
    try:
        user = auth_controller.signup(db, payload)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return auth_controller.login(db, payload.email, payload.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return auth_controller.refresh_access_token(db, payload.refresh_token)
    except InvalidRefreshTokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    auth_controller.logout(db, payload.refresh_token)
    return MessageResponse(message="Logged out successfully")
