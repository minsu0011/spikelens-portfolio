import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.session import get_db
from app.models import User, UserSession

password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
SESSION_COOKIE = "spikelens_session"
CSRF_COOKIE = "spikelens_csrf"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def verify_password(encoded: str, password: str) -> bool:
    try:
        return password_hasher.verify(encoded, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def check_origin(request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in get_settings().allowed_origins:
        raise AppError(403, "INVALID_ORIGIN", "Request origin is not allowed")


def session_user(request: Request, db: Session):
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 200:
        return None
    row = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == digest(token), UserSession.expires_at > datetime.now(UTC)
        )
    )
    if not row:
        return None
    user = db.get(User, row.user_id)
    request.state.auth_session = row
    return user


def optional_user(request: Request, db: Session = Depends(get_db)):
    return session_user(request, db)


def require_user(request: Request, db: Session = Depends(get_db)):
    user = session_user(request, db)
    if not user:
        raise AppError(401, "AUTH_REQUIRED", "Please sign in")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
        csrf_header = request.headers.get("x-csrf-token", "")
        expected = request.state.auth_session.csrf_hash
        if (
            not csrf_cookie
            or not secrets.compare_digest(csrf_cookie, csrf_header)
            or not secrets.compare_digest(digest(csrf_header), expected)
        ):
            raise AppError(403, "CSRF_FAILED", "CSRF verification failed")
    return user


def require_admin(user: User = Depends(require_user)):
    if user.role != "admin":
        raise AppError(403, "ADMIN_REQUIRED", "Administrator access is required")
    return user


def issue_session(db: Session, user: User, response):
    settings = get_settings()
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    for name, value, httponly in [(SESSION_COOKIE, token, True), (CSRF_COOKIE, csrf, False)]:
        response.set_cookie(
            name,
            value,
            httponly=httponly,
            secure=settings.cookie_secure,
            samesite="lax",
            max_age=settings.session_ttl_seconds,
            path="/",
        )


def clear_cookies(response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
