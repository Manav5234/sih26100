"""CLI: create an officer with a hashed password. Idempotent — safe to re-run.

Usage (any directory, no env vars needed — app/config.py reads backend/.env):
    python backend/scripts/create_officer.py --name "Priya Sharma" \
        --email priya@example.gov.in --password secret123 --role inspector

Exit codes: 0 = created or already exists, 1 = could not reach the database.
"""
import argparse
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import settings
from app.database import engine
from app.db.models import Officer, OfficerRole


def database_target() -> str:
    """host/port/db this script will try — never the password."""
    try:
        url = make_url(settings.database_url)
    except Exception:
        return "an unparseable DATABASE_URL (check backend/.env)"
    return f"{url.host}:{url.port or 'default'}/{url.database or '?'}"


def _first_line(exc: Exception) -> str:
    text = str(exc).strip().splitlines()
    return (text[0] if text else type(exc).__name__)[:160]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an officer account")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", choices=["admin", "inspector", "viewer"], default="inspector")
    args = parser.parse_args()

    try:
        with Session(engine) as session:
            existing = session.query(Officer).filter_by(email=args.email).first()
            if existing:
                # idempotent: re-running the same command is not an error
                print(f"already exists: {args.email} "
                      f"(role={existing.role.value}, id={existing.id})")
                return 0

            officer = Officer(
                id=uuid.uuid4(),
                name=args.name,
                email=args.email,
                password_hash=hash_password(args.password),
                role=OfficerRole(args.role.upper()),
            )
            session.add(officer)
            session.commit()
            print(f"created officer: {args.email} (role={args.role}, id={officer.id})")
            return 0
    except (OperationalError, OSError) as exc:
        # One line, no traceback: DNS failure, refused connection, auth error.
        print(f"ERROR: cannot reach the database at {database_target()} — "
              f"set DATABASE_URL in backend/.env or start Postgres "
              f"(docker compose up postgres). [{_first_line(exc)}]",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
