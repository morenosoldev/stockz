"""Market data protocol interface for pluggable data providers.

This module defines the abstract interface that all market data providers must implement,
enabling easy swapping between providers (Twelve Data, Yahoo Finance, etc.).
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Protocol

from .attribution import Attribution, DataSource


class MarketDataProvider(Enum):
    """Supported market data providers."""

    TWELVE_DATA = "twelve_data"
    YAHOO_FINANCE = "yahoo_finance"
    ALPHA_VANTAGE = "alpha_vantage"


@dataclass
class OHLCVBar:
    """Single OHLCV bar with attribution."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    attribution: Attribution


@dataclass
class TickerInfo:
    """Ticker information and metadata."""

    symbol: str
    name: str | None = None
    exchange: str | None = None
    currency: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    attribution: Attribution | None = None


class MarketDataProtocol(Protocol):
    """Protocol interface for market data providers.

    All market data adapters must implement this interface to ensure
    consistent behavior across different data sources.
    """

    @property
    def provider_name(self) -> str:
        """Return the name of the data provider."""
        ...

    @property
    def data_source(self) -> DataSource:
        """Return the DataSource enum value for attribution."""
        ...

    def get_ohlcv(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: str = "1d",
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV (Open, High, Low, Close, Volume) data.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL", "TSLA")
            start_date: Start date for data range (optional)
            end_date: End date for data range (optional)
            interval: Time interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)
            limit: Maximum number of bars to return (optional)

        Returns:
            List of OHLCVBar objects with attribution

        Raises:
            ValueError: If ticker is invalid or parameters are incorrect
            ConnectionError: If API request fails
        """
        ...

    def validate_ticker(self, ticker: str) -> bool:
        """Validate if a ticker symbol exists and is tradeable.

        Args:
            ticker: Stock ticker symbol to validate

        Returns:
            True if ticker is valid and tradeable, False otherwise
        """
        ...

    def get_ticker_info(self, ticker: str) -> TickerInfo | None:
        """Get detailed information about a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            TickerInfo object with company details and attribution, or None if not found
        """
        ...

    def search_symbol(self, query: str, limit: int = 10) -> list[TickerInfo]:
        """Search for ticker symbols by company name or partial symbol.

        Args:
            query: Search query (company name or partial symbol)
            limit: Maximum number of results to return

        Returns:
            List of TickerInfo objects matching the query
        """
        ...

    def get_attribution(self) -> Attribution:
        """Get attribution metadata for the last API call.

        Returns:
            Attribution object with source, timestamp, and metadata
        """
        ...

    def health_check(self) -> bool:
        """Check if the data provider API is accessible and responsive.

        Returns:
            True if API is healthy, False otherwise
        """
        ...
