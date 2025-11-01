"""Database connection and session management.

This module provides database configuration, connection pooling,
and session management for the Recover-Bot application.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from src.ops.config import get_config


# SQLAlchemy 2.0 declarative base
class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


# Load database configuration from config/env
config = get_config()

# Create engine with connection pooling
engine = create_engine(
    config.database.url,
    pool_size=config.database.pool_size,
    max_overflow=config.database.max_overflow,
    pool_timeout=config.database.pool_timeout,
    pool_recycle=config.database.pool_recycle,
    pool_pre_ping=True,  # Verify connections before using
    echo=config.database.echo,
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
