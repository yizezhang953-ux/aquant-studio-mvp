from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import User
from app.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_session,
    create_user,
    get_current_user,
    revoke_user_sessions,
)


router = APIRouter()


@router.post("/register", response_model=AuthResponse)
def register(request: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = create_user(db, request.email, request.password, request.display_name)
    session = create_session(db, user)
    return _auth_response(user, session.token, session.expires_at)


@router.post("/login", response_model=AuthResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = authenticate_user(db, request.email, request.password)
    session = create_session(db, user)
    return _auth_response(user, session.token, session.expires_at)


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return _user_response(current_user)


@router.post("/logout")
def logout(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    revoke_user_sessions(db, current_user)
    return {"status": "logged_out"}


def _auth_response(user: User, token: str, expires_at) -> AuthResponse:
    return AuthResponse(
        access_token=token,
        expires_at=expires_at,
        user=_user_response(user),
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )
