"""
Seed script — creates test accounts for the Customer Survey System.

Usage:
    python seed.py

Requires DATABASE_URL to be set in your environment or a .env file.
"""

import uuid
from app.database import SessionLocal, engine, Base
from app.models import User, UserRole
from app.security import hash_password

TEST_ACCOUNTS = [
    {
        "email": "admin@css.com",
        "full_name": "CSS Administrator",
        "password": "Password123!",
        "role": UserRole.admin,
    },
    {
        "email": "manager1@css.com",
        "full_name": "Alice Manager",
        "password": "Password123!",
        "role": UserRole.manager,
    },
    {
        "email": "manager2@css.com",
        "full_name": "Bob Manager",
        "password": "Password123!",
        "role": UserRole.manager,
    },
]


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        created = 0
        skipped = 0
        for account in TEST_ACCOUNTS:
            existing = db.query(User).filter(User.email == account["email"]).first()
            if existing:
                print(f"  [skip]    {account['email']} already exists")
                skipped += 1
                continue

            user = User(
                id=str(uuid.uuid4()),
                email=account["email"],
                full_name=account["full_name"],
                hashed_password=hash_password(account["password"]),
                role=account["role"],
                is_active=True,
                is_approved=True,
            )
            db.add(user)
            created += 1
            print(f"  [created] {account['email']}  ({account['role'].value})")

        db.commit()
        print(f"\nDone — {created} created, {skipped} skipped.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
