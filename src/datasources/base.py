"""Base interfaces and utilities for data adapters.

This module defines the core interface that all data adapters must implement,
including attribution tracking, error handling, and caching patterns.

All data fetched through adapters must include proper attribution metadata
to ensure reproducibility and compliance with data provider terms.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from src.ops.logging import get_logger

logger = get_logger(__name__)


class DataSource(str, Enum):
    """Enumeration of supported data sources.

    Each data source must be registered here for tracking and attribution.
    """

    YAHOO_FINANCE = "yahoo_finance"
    TWELVE_DATA = "twelve_data"
    ALPHA_VANTAGE = "alpha_vantage"
    FINNHUB = "finnhub"
    NEWS_API = "news_api"
    CHATBOT_RESEARCH = "chatbot_research"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


@dataclass
class Attribution:
    """Attribution metadata for data points.

    Every piece of data fetched from external sources must include
    attribution information for reproducibility and compliance.

    Attributes:
        source: Data source identifier
        timestamp: When the data was fetched (UTC)
        url: Optional URL of the data source endpoint
        api_endpoint: Optional API endpoint path
        version: Data schema version (default: "1.0")
        metadata: Optional additional metadata (e.g., rate limits, request ID)

    Example:
        >>> from datetime import datetime, timezone
        >>> attr = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc),
        ...     url="https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
        ...     version="1.0"
        ... )
    """

    source: DataSource
    timestamp: datetime
    url: str | None = None
    api_endpoint: str | None = None
    version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate attribution fields."""
        if not isinstance(self.source, DataSource):
            raise TypeError(f"source must be DataSource enum, got {type(self.source)}")
        if not isinstance(self.timestamp, datetime):
            raise TypeError(f"timestamp must be datetime, got {type(self.timestamp)}")


class DataAdapterError(Exception):
    """Base exception for data adapter errors."""

    def __init__(
        self,
        message: str,
        source: DataSource | None = None,
        original_error: Exception | None = None,
    ):
        """Initialize data adapter error.

        Args:
            message: Error description
            source: Data source where error occurred
            original_error: Original exception if wrapping another error
        """
        super().__init__(message)
        self.source = source
        self.original_error = original_error


class RateLimitError(DataAdapterError):
    """Exception raised when rate limit is exceeded."""

    pass


class AuthenticationError(DataAdapterError):
    """Exception raised when authentication fails."""

    pass


class DataNotFoundError(DataAdapterError):
    """Exception raised when requested data is not available."""

    pass


@runtime_checkable
class DataAdapterProtocol(Protocol):
    """Protocol for all data adapters.

    All data adapters must implement this interface to ensure consistent
    behavior across different data sources.

    Implementers must handle:
    - Attribution tracking for all fetched data
    - Error handling with retries and fallbacks
    - Rate limiting and backoff
    - Caching when appropriate

    Example:
        >>> class PriceAdapter:
        ...     source = DataSource.YAHOO_FINANCE
        ...
        ...     def fetch(self, ticker: str, **kwargs) -> dict[str, Any]:
        ...         # Fetch and return data with attribution
        ...         return {"data": [...], "attribution": {...}}
        ...
        ...     def get_attribution(self) -> Attribution:
        ...         return Attribution(
        ...             source=self.source,
        ...             timestamp=datetime.now(timezone.utc)
        ...         )
    """

    source: DataSource

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Fetch data from the adapter's source.

        Args:
            *args: Positional arguments specific to the adapter
            **kwargs: Keyword arguments specific to the adapter

        Returns:
            Fetched data with attribution metadata

        Raises:
            DataAdapterError: If data cannot be fetched
            RateLimitError: If rate limit is exceeded
            AuthenticationError: If authentication fails
        """
        ...

    def get_attribution(self) -> Attribution:
        """Get attribution metadata for the last fetch operation.

        Returns:
            Attribution metadata for the last fetch
        """
        ...


class BaseDataAdapter(ABC):
    """Abstract base class for data adapters.

    Provides common functionality for all data adapters including:
    - Logging
    - Attribution tracking
    - Basic error handling

    Subclasses must implement:
    - fetch() method for data retrieval
    - _build_attribution() method for attribution metadata

    Attributes:
        source: Data source identifier
        logger: Structured logger instance
        _last_attribution: Attribution from last fetch operation

    Example:
        >>> class MyAdapter(BaseDataAdapter):
        ...     source = DataSource.YAHOO_FINANCE
        ...
        ...     def fetch(self, ticker: str) -> dict[str, Any]:
        ...         data = self._fetch_from_api(ticker)
        ...         self._last_attribution = self._build_attribution(
        ...             url=f"https://api.example.com/{ticker}"
        ...         )
        ...         return data
        ...
        ...     def _build_attribution(self, **metadata) -> Attribution:
        ...         return Attribution(
        ...             source=self.source,
        ...             timestamp=datetime.now(timezone.utc),
        ...             **metadata
        ...         )
    """

    source: DataSource

    def __init__(self) -> None:
        """Initialize base data adapter."""
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
        self._last_attribution: Attribution | None = None

    @abstractmethod
    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Fetch data from the adapter's source.

        Must be implemented by subclasses.

        Args:
            *args: Positional arguments specific to the adapter
            **kwargs: Keyword arguments specific to the adapter

        Returns:
            Fetched data with attribution metadata

        Raises:
            DataAdapterError: If data cannot be fetched
        """
        raise NotImplementedError("Subclasses must implement fetch()")

    @abstractmethod
    def _build_attribution(self, **metadata: Any) -> Attribution:
        """Build attribution metadata for fetched data.

        Must be implemented by subclasses.

        Args:
            **metadata: Additional metadata for attribution

        Returns:
            Attribution metadata
        """
        raise NotImplementedError("Subclasses must implement _build_attribution()")

    def get_attribution(self) -> Attribution:
        """Get attribution metadata for the last fetch operation.

        Returns:
            Attribution metadata for the last fetch

        Raises:
            ValueError: If no fetch operation has been performed yet
        """
        if self._last_attribution is None:
            raise ValueError("No fetch operation performed yet")
        return self._last_attribution

    def validate_data(self, data: Any) -> bool:
        """Validate fetched data.

        Override this method to add adapter-specific validation logic.

        Args:
            data: Data to validate

        Returns:
            True if data is valid, False otherwise
        """
        return data is not None
