from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import User, UserSession

LEGACY_ITERATIONS = 120_000


# --------------------------------------------------------------------------- passwords


def hash_password(password: str, iterations: int | None = None) -> str:
    """``pbkdf2_sha256$<iterations>$<salt>$<digest>`` (OWASP 2023: 600k iterations for SHA-256)."""
    iterations = iterations or settings.password_hash_iterations
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def _parse_hash(password_hash: str) -> tuple[int, bytes, bytes] | None:
    parts = password_hash.split("$")
    try:
        if len(parts) == 4 and parts[0] == "pbkdf2_sha256":
            return int(parts[1]), base64.b64decode(parts[2]), base64.b64decode(parts[3])
        if len(parts) == 3 and parts[0] == "pbkdf2_sha256":  # v0.1 format, fixed 120k iterations
            return LEGACY_ITERATIONS, base64.b64decode(parts[1]), base64.b64decode(parts[2])
    except (ValueError, TypeError):
        return None
    return None


def verify_password(password: str, password_hash: str) -> bool:
    parsed = _parse_hash(password_hash)
    if parsed is None:
        return False
    iterations, salt, expected = parsed
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def needs_rehash(password_hash: str) -> bool:
    """True for the v0.1 format or when fewer iterations than configured were used."""
    parsed = _parse_hash(password_hash)
    return parsed is None or password_hash.count("$") != 3 or parsed[0] < settings.password_hash_iterations


# --------------------------------------------------------------------------- login throttling

_failures: dict[str, list[float]] = {}
_failures_lock = threading.Lock()


def _recent_failures(key: str) -> list[float]:
    window = settings.login_lockout_minutes * 60
    now = time.monotonic()
    with _failures_lock:
        attempts = [t for t in _failures.get(key, []) if now - t < window]
        _failures[key] = attempts
        return attempts


def _record_failure(key: str) -> None:
    with _failures_lock:
        _failures.setdefault(key, []).append(time.monotonic())


def _clear_failures(key: str) -> None:
    with _failures_lock:
        _failures.pop(key, None)


def reset_login_throttle() -> None:
    with _failures_lock:
        _failures.clear()


# --------------------------------------------------------------------------- users and sessions


_DUMMY_HASH = None


def _dummy_verify(password: str) -> None:
    """Spend the same PBKDF2 time for unknown e-mails so timing does not reveal registered accounts."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(12))
    verify_password(password, _DUMMY_HASH)


def set_admin(db: Session, email: str, is_admin: bool = True) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        raise ValueError(f"no account for {email}")
    user.is_admin = is_admin
    db.commit()
    db.refresh(user)
    return user


def create_user(db: Session, email: str, password: str, display_name: str) -> User:
    if not settings.allow_registration:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registration is disabled")
    normalized_email = email.strip().lower()
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    first_user = (db.scalar(select(func.count()).select_from(User)) or 0) == 0
    user = User(
        email=normalized_email,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_admin=first_user and settings.first_user_admin_enabled,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str, client: str = "") -> User:
    normalized_email = email.strip().lower()
    throttle_key = f"{normalized_email}|{client}"
    if len(_recent_failures(throttle_key)) >= settings.login_max_failures:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed logins; try again in {settings.login_lockout_minutes} minutes",
        )
    user = db.scalar(select(User).where(User.email == normalized_email))
    if user is None:
        _dummy_verify(password)
    if user is None or not user.is_active or not verify_password(password, user.password_hash):
        _record_failure(throttle_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    _clear_failures(throttle_key)
    changed = False
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
        changed = True
    if changed:
        db.commit()
        db.refresh(user)
    return user


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[UserSession, str]:
    """Returns the session row and the bearer token (only its SHA-256 is stored)."""
    token = secrets.token_urlsafe(48)
    session = UserSession(
        user_id=user.id,
        token=token_digest(token),
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=settings.auth_token_ttl_hours),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session, token


def _bearer(authorization: str | None) -> str | None:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    return authorization.split(" ", 1)[1].strip() or None


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer(authorization)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    session = db.scalar(select(UserSession).where(UserSession.token == token_digest(token)))
    now = datetime.now(UTC).replace(tzinfo=None)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User is not active")
    return user


def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator role required")
    return current_user


def revoke_user_sessions(db: Session, user: User) -> None:
    now = datetime.now(UTC).replace(tzinfo=None)
    sessions = db.scalars(
        select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))
    ).all()
    for session in sessions:
        session.revoked_at = now
    db.commit()
