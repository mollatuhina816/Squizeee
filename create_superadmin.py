import os
from getpass import getpass

from pwdlib import PasswordHash
from sqlalchemy import create_engine, text

print("\n=== QUIZEEE SUPER ADMIN SETUP ===\n")

name = input("Admin Name: ").strip()
email = input("Admin Email: ").strip().lower()
password = getpass("Admin Password: ")
confirm = getpass("Confirm Password: ")

if not name or not email or "@" not in email:
    raise SystemExit("Valid name and email required.")

if len(password) < 12 or password != confirm:
    raise SystemExit("Password must be at least 12 characters and match.")

hashed_password = PasswordHash.recommended().hash(password)

engine = create_engine(os.environ["DATABASE_URL"])

with engine.begin() as conn:
    existing = conn.execute(
        text("SELECT id FROM users WHERE lower(email) = :email"),
        {"email": email},
    ).first()

    if existing:
        raise SystemExit("This email already exists.")

    admin = conn.execute(
        text("""
            INSERT INTO users
                (id, name, email, profession,
                 password_hash, is_super_admin)
            VALUES
                (gen_random_uuid(), :name, :email,
                 'teacher', :password_hash, TRUE)
            RETURNING email, is_super_admin
        """),
        {
            "name": name,
            "email": email,
            "password_hash": hashed_password,
        },
    ).first()

print("\nSuper Admin created successfully!")
print("Email:", admin.email)
print("Super Admin:", admin.is_super_admin)
