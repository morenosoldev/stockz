"""Database connection and session management.

This module provides database configuration, connection pooling,
and session management for the Recover-Bot application.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# SQLAlchemy 2.0 declarative base
class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Database configuration (will be replaced with config in Task 1.5)
DATABASE_URL = "postgresql://recoverbot:recoverbot@localhost:5432/recoverbot"

# Create engine with connection pooling
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # Max 10 connections in pool
    max_overflow=20,  # Allow up to 20 overflow connections
    pool_pre_ping=True,  # Verify connections before using
    echo=False,  # Set to True for SQL query logging
)

# Session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Get database session.

    Yields:
        Database session that will be automatically closed after use.

    Example:
        ```python
        from src.storage.database import get_db

        with next(get_db()) as db:
            candidates = db.query(Candidate).all()
        ```

        Or with FastAPI dependency injection:
        ```python
        @app.get("/candidates")
        async def list_candidates(db: Session = Depends(get_db)):
            return db.query(Candidate).all()
        ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database schema.

    Creates all tables defined in models if they don't exist.
    For production, use Alembic migrations instead.
    """
    from src.storage import models  # noqa: F401 - Import to register models

    Base.metadata.create_all(bind=engine)
