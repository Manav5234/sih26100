import os
import tempfile
import logging
import uuid
import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from app.config import settings

# CRITICAL: All model classes must be imported here before Base.metadata.create_all
from app.db.models import (
    Base,
    Officer,
    OfficerRole,
    Tender,
    Requirement,
    Bidder,
    Document,
    ExtractedField,
    Verification,
    RuleResult,
    Decision,
    AuditEvent,
)
from app.seed import seed_demo_data

logger = logging.getLogger(__name__)

# Determine DATABASE_URL from env or settings fallback
db_url = os.environ.get("DATABASE_URL") or settings.database_url

# Fix legacy postgres:// URL prefix to postgresql://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

is_vercel = bool(os.environ.get("VERCEL"))

# If running on Vercel without a cloud DATABASE_URL set, fallback to SQLite in /tmp for demo
if is_vercel and ("localhost" in db_url or "127.0.0.1" in db_url or "postgres:5432" in db_url):
    db_path = os.path.join(tempfile.gettempdir(), "app.db")
    db_url = f"sqlite:///{db_path}"

# Configure Engine & Pooling options based on database dialect & environment
is_sqlite = "sqlite" in db_url

engine_kwargs = {}
if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    if is_vercel:
        engine_kwargs["poolclass"] = NullPool
    else:
        engine_kwargs["pool_pre_ping"] = True

engine = create_engine(db_url, **engine_kwargs)


def get_db() -> Session:
    """Dependency that provides a SQLAlchemy session."""
    db = Session(engine)
    return db


def init_db() -> None:
    """Create all database tables and seed initial demo data idempotently."""
    try:
        logger.info("Initializing database schema via create_all on %s...", db_url.split("@")[-1])
        Base.metadata.create_all(engine)

        with Session(engine) as session:
            # 1. Seed Officer
            existing_officer = (
                session.query(Officer).filter(Officer.email.ilike("priya@example.gov.in")).first()
            )
            if not existing_officer:
                pass_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
                officer = Officer(
                    id=uuid.uuid4(),
                    name="Priya Sharma",
                    email="priya@example.gov.in",
                    password_hash=pass_hash,
                    role=OfficerRole.INSPECTOR,
                )
                session.add(officer)
                session.commit()
                logger.info("Seeded default officer priya@example.gov.in")

            # 2. Seed Demo Tenders & Bidders if database is empty
            seed_demo_data(session)

    except Exception as exc:
        logger.error("Database startup initialization warning/error: %s", exc, exc_info=True)


# Execute init_db at module load time for fast serverless availability
init_db()
