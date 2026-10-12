"""Local operator CLI; no public role-changing endpoint or fixed admin credentials."""

import argparse

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog, User


def promote(email: str):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if not user:
            raise SystemExit("Register this account first; no user was changed")
        user.role = "admin"
        db.add(
            AuditLog(user_id=user.id, action="operator_promoted_admin", resource_id=str(user.id))
        )
        db.commit()
    print("Existing account promoted to administrator")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Promote an existing local account to administrator"
    )
    parser.add_argument("--email", required=True)
    promote(parser.parse_args().email)
