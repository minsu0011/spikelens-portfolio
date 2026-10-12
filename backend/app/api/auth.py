from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.core.security import (
    check_origin,
    clear_cookies,
    digest,
    issue_session,
    password_hasher,
    require_user,
    verify_password,
)
from app.db.session import get_db
from app.models import AuditLog, User
from app.schemas.auth import LoginInput, RegisterInput, UserOutput

router = APIRouter(prefix="/auth", tags=["Authentication"])


def protect_attempt(request: Request, db: Session, email: str):
    # Account limits keep unrelated users behind the same Next.js peer independent.
    # The higher peer ceiling still bounds random-account abuse. Never trust X-Forwarded-For.
    peer = digest(request.client.host if request.client else "unknown")
    account = digest(email.strip().lower())
    # Serialize both counters so concurrent attempts cannot race past either budget.
    locks = sorted(
        {int.from_bytes(bytes.fromhex(value)[:8], "big", signed=True) for value in (peer, account)}
    )
    for lock in locks:
        db.execute(text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": lock})
    since = datetime.now(UTC) - timedelta(minutes=15)
    attempts = [AuditLog.action == "auth_attempt", AuditLog.created_at >= since]
    account_count = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(*attempts, AuditLog.resource_id == account)
        )
        or 0
    )
    peer_count = (
        db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(
                *attempts,
                or_(
                    AuditLog.details["peer_digest"].as_string() == peer,
                    AuditLog.resource_id == peer,
                ),
            )
        )
        or 0
    )
    if account_count >= 20 or peer_count >= 200:
        raise AppError(429, "RATE_LIMITED", "Too many authentication attempts; try later")
    db.add(AuditLog(action="auth_attempt", resource_id=account, details={"peer_digest": peer}))
    db.commit()


@router.post("/register", response_model=UserOutput, status_code=201)
def register(
    data: RegisterInput, request: Request, response: Response, db: Session = Depends(get_db)
):
    check_origin(request)
    protect_attempt(request, db, str(data.email))
    user = User(
        email=str(data.email).lower(),
        name=data.name.strip() or "Demo user",
        password_hash=password_hasher.hash(data.password),
        role="user",
    )
    db.add(user)
    try:
        db.flush()
        issue_session(db, user, response)
        db.add(AuditLog(user_id=user.id, action="user_registered"))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise AppError(409, "EMAIL_EXISTS", "An account already uses this email") from exc
    return user


@router.post("/login", response_model=UserOutput)
def login(data: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    check_origin(request)
    protect_attempt(request, db, str(data.email))
    user = db.scalar(select(User).where(User.email == str(data.email).lower()))
    # Always perform an Argon2 verification to reduce account-existence timing differences.
    encoded = user.password_hash if user else DUMMY_HASH
    valid = verify_password(encoded, data.password)
    if not user or not valid:
        raise AppError(401, "INVALID_CREDENTIALS", "Email or password is incorrect")
    issue_session(db, user, response)
    db.add(AuditLog(user_id=user.id, action="user_login"))
    db.commit()
    return user


DUMMY_HASH = password_hasher.hash("dummy-password-not-an-account")


@router.get("/me", response_model=UserOutput)
def me(user: User = Depends(require_user)):
    return user


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    db.delete(request.state.auth_session)
    db.add(AuditLog(user_id=user.id, action="user_logout"))
    db.commit()
    clear_cookies(response)
