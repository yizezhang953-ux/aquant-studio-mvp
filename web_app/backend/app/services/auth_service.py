from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserSession


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, salt_text, digest_text = password_hash.split("$", 2)
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    salt = base64.b64decode(salt_text.encode())
    expected = base64.b64decode(digest_text.encode())
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return hmac.compare_digest(actual, expected)


def create_user(db: Session, email: str, password: str, display_name: str) -> User:
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return user


def create_session(db: Session, user: User) -> UserSession:
    token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user.id,
        token=token,
        expires_at=datetime.now(UTC).replace(tzinfo=None)
        + timedelta(hours=settings.auth_token_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    session = db.scalar(select(UserSession).where(UserSession.token == token))
    now = datetime.now(UTC).replace(tzinfo=None)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


def revoke_user_sessions(db: Session, user: User) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sessions = db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = now
    db.commit()
