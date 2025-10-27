"""Test suite configuration and fixtures."""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.storage.database import Base


@pytest.fixture(scope="function")
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database for testing."""
    # Create in-memory SQLite database
    engine = create_engine("sqlite:///:memory:")

    # Create all tables
    Base.metadata.create_all(engine)

    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@pytest.fixture
def sample_ticker() -> str:
    """Return a sample ticker symbol for testing."""
    return "AAPL"


@pytest.fixture
def sample_tickers() -> list[str]:
    """Return a list of sample ticker symbols for testing."""
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
