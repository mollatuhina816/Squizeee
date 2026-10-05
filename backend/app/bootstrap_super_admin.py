import argparse
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import AuditEvent, User
from .security import passwords


def ensure_no_super_admin(db: Session):
    if db.bind and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(731946205183)"))
    if db.scalar(select(User.id).where(User.is_super_admin.is_(True)).limit(1)):
        raise ValueError("A super admin is already configured")


def audit_promotion(db: Session, user: User):
    db.add(AuditEvent(actor_id=user.id, organization_id=None,
                      action="super_admin.bootstrapped", resource_id=str(user.id)))


def promote_first_super_admin(db: Session, email: str) -> str:
    normalized_email = email.strip().casefold()
    if not normalized_email:
        raise ValueError("An email address is required")
    ensure_no_super_admin(db)

    user = db.scalar(select(User).where(User.email == normalized_email).with_for_update())
    if not user:
        raise ValueError("No registered account has that email address")
    if not user.active:
        raise ValueError("The account is disabled")
    user.is_super_admin = True
    audit_promotion(db, user)
    db.flush()
    return user.email


def create_first_super_admin(db: Session, name: str, email: str, password: str) -> User:
    name = name.strip()
    normalized_email = email.strip().casefold()
    if not name or len(name) > 120:
        raise ValueError("Name must contain 1 to 120 characters")
    try:
        normalized_email = str(TypeAdapter(EmailStr).validate_python(normalized_email)).casefold()
    except ValidationError as error:
        raise ValueError("Enter a valid email address") from error
    if len(password) < 6 or len(password) > 128:
        raise ValueError("Password must contain 6 to 128 characters")
    if not (any(char.islower() for char in password)
            and any(char.isupper() for char in password)
            and any(char.isdigit() for char in password)
            and any(not char.isalnum() for char in password)):
        raise ValueError("Password must include lowercase and uppercase letters, a number, and a symbol")

    ensure_no_super_admin(db)
    if db.scalar(select(User.id).where(User.email == normalized_email)):
        raise ValueError("An account with that email already exists; use the promote command instead")
    user = User(name=name, email=normalized_email, profession="teacher",
                password_hash=passwords.hash(password), is_super_admin=True)
    db.add(user)
    db.flush()
    audit_promotion(db, user)
    db.flush()
    return user


def main():
    parser = argparse.ArgumentParser(description="Create or promote the first Quizeee super-admin account.")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Create a new super-admin account")
    create.add_argument("name", help="Display name")
    create.add_argument("email", help="Login email address")
    promote = commands.add_parser("promote", help="Promote an existing account")
    promote.add_argument("email", help="Email address of the existing account")
    args = parser.parse_args()
    try:
        if args.command == "create":
            password = getpass("New super-admin password: ")
            confirmation = getpass("Confirm password: ")
            if password != confirmation:
                parser.error("Passwords do not match")
        with SessionLocal.begin() as db:
            if args.command == "create":
                user = create_first_super_admin(db, args.name, args.email, password)
                account_id, email = user.id, user.email
            else:
                email = promote_first_super_admin(db, args.email)
                user = db.scalar(select(User).where(User.email == email))
                account_id = user.id
    except ValueError as error:
        parser.error(str(error))
    print(f"Super admin account ready: {email} (ID: {account_id}). Sign in, then open /admin.")


if __name__ == "__main__":
    main()