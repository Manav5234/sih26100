import os
import tempfile
import logging
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.config import settings
from app.db.models import Base, Officer, OfficerRole

logger = logging.getLogger(__name__)

db_url = settings.database_url
is_vercel = bool(os.environ.get("VERCEL"))

# If running on Vercel without a cloud DATABASE_URL set, fallback to SQLite in /tmp for demo
if is_vercel and ("localhost" in db_url or "127.0.0.1" in db_url or "postgres:5432" in db_url):
    db_path = os.path.join(tempfile.gettempdir(), "sih26100.db")
    db_url = f"sqlite:///{db_path}"

engine = create_engine(
    db_url,
    pool_pre_ping=True if "sqlite" not in db_url else False,
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
)

# Auto-create tables and seed default demo officer for SQLite fallback
if "sqlite" in db_url:
    try:
        from app.auth import hash_password

        Base.metadata.create_all(engine)
        with Session(engine) as session:
            existing = session.query(Officer).filter_by(email="priya@example.gov.in").first()
            if not existing:
                officer = Officer(
                    id=uuid.uuid4(),
                    name="Priya Sharma",
                    email="priya@example.gov.in",
                    password_hash=hash_password("secret123"),
                    role=OfficerRole.INSPECTOR,
                )
                session.add(officer)
                session.commit()
    except Exception as exc:
        logger.warning("sqlite_init_warning: %s", exc)


def get_db() -> Session:
    """Dependency that provides a SQLAlchemy session."""
    db = Session(engine)
    return db
