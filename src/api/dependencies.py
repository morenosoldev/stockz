"""FastAPI dependency injection functions.

Provides reusable dependencies for database sessions, configuration,
and other shared resources across API endpoints.
"""

from collections.abc import Generator

from sqlalchemy.orm import Session

from src.ops.config import Config, get_config
from src.storage.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """Dependency to get database session.

    Yields:
        SQLAlchemy database session

    Usage:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_app_config() -> Config:
    """Dependency to get application configuration.

    Returns:
        Application configuration instance

    Usage:
        @app.get("/endpoint")
        def endpoint(config: Config = Depends(get_app_config)):
            ...
    """
    return get_config()


# Future dependencies can be added here:
# - def get_current_user() -> User - for authentication
# - def get_price_adapter() -> PriceAdapter - for data access
# - def get_strategy_registry() -> StrategyRegistry - for strategy access
# - def rate_limiter() - for API rate limiting
