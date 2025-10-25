"""Price data adapter for fetching market data.

This module provides the PriceAdapter for fetching OHLCV (Open, High, Low, Close, Volume)
data from Yahoo Finance using the yfinance library.

All data includes proper attribution and caching for performance.
"""

import time
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFException

from src.datasources.attribution import create_attribution
from src.datasources.base import (
    Attribution,
    BaseDataAdapter,
    DataAdapterError,
    DataNotFoundError,
    DataSource,
    RateLimitError,
)
from src.datasources.cache import Cache
from src.ops.config import get_config
from src.ops.logging import get_logger

logger = get_logger(__name__)


# Default ticker universe for MVP (top liquid US stocks)
DEFAULT_UNIVERSE = [
    # Tech Giants
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "NVDA",
    "TSLA",
    # Financial
    "JPM",
    "BAC",
    "WFC",
    "GS",
    "MS",
    # Healthcare
    "JNJ",
    "UNH",
    "PFE",
    "ABBV",
    # Consumer
    "WMT",
    "HD",
    "DIS",
    "NKE",
    "SBUX",
    # Industrial
    "BA",
    "CAT",
    "GE",
    # Energy
    "XOM",
    "CVX",
    # Communication
    "VZ",
    "T",
]


class PriceDataError(DataAdapterError):
    """Exception raised when price data cannot be fetched or is invalid."""

    pass


class PriceAdapter(BaseDataAdapter):
    """Adapter for fetching price data from Yahoo Finance.

    Provides methods for:
    - Getting ticker universe
    - Fetching OHLCV bars
    - Getting latest prices
    - Retrieving ticker information

    All data is cached and includes proper attribution.

    Attributes:
        source: Data source identifier (YAHOO_FINANCE)
        cache: Cache instance for storing fetched data
        config: Application configuration

    Example:
        >>> adapter = PriceAdapter()
        >>> bars = adapter.get_bars("AAPL", window=20)
        >>> print(bars.head())
        >>> attribution = adapter.get_attribution()
    """

    source = DataSource.YAHOO_FINANCE

    def __init__(self, cache: Cache | None = None):
        """Initialize price adapter.

        Args:
            cache: Optional cache instance (creates default if not provided)
        """
        super().__init__()
        self.config = get_config()

        # Initialize cache
        if cache is None:
            cache_config = self.config.datasources.cache
            self.cache = Cache(
                cache_dir=cache_config.cache_dir,
                ttl_seconds=cache_config.ttl_seconds,
                use_compression=cache_config.use_compression,
            )
        else:
            self.cache = cache

        self.logger.info(
            "PriceAdapter initialized",
            source=self.source.value,
            cache_dir=str(self.cache.cache_dir),
            cache_ttl=self.cache.ttl_seconds,
        )

    def get_universe(
        self, min_market_cap: float | None = None, min_volume: int | None = None
    ) -> list[str]:
        """Get list of tickers to scan.

        For MVP, returns a curated list of liquid US stocks.
        In future versions, this could be expanded to:
        - Load from CSV file
        - Query from database
        - Filter by market cap, volume, sector
        - Include international stocks

        Args:
            min_market_cap: Minimum market cap filter (not implemented in MVP)
            min_volume: Minimum volume filter (not implemented in MVP)

        Returns:
            List of ticker symbols

        Example:
            >>> adapter = PriceAdapter()
            >>> tickers = adapter.get_universe()
            >>> len(tickers) > 20
            True
        """
        self.logger.info(
            "Getting ticker universe",
            min_market_cap=min_market_cap,
            min_volume=min_volume,
            universe_size=len(DEFAULT_UNIVERSE),
        )

        # For MVP, return default universe
        # TODO: Implement filtering by market cap and volume
        return DEFAULT_UNIVERSE.copy()

    def get_bars(
        self,
        ticker: str,
        window: int = 20,
        interval: str = "1d",
    ) -> pd.DataFrame:
        """Fetch OHLCV bars for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            window: Number of bars to fetch (default: 20)
            interval: Data interval (1d, 1h, etc.) (default: "1d")

        Returns:
            DataFrame with columns: Open, High, Low, Close, Volume
            Index is DatetimeIndex

        Raises:
            PriceDataError: If data cannot be fetched
            DataNotFoundError: If ticker is invalid or has no data

        Example:
            >>> adapter = PriceAdapter()
            >>> bars = adapter.get_bars("AAPL", window=20)
            >>> assert len(bars) <= 20
            >>> assert "Close" in bars.columns
        """
        # Check cache first
        cache_key = {"ticker": ticker, "window": window, "interval": interval}
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for bars", ticker=ticker, window=window)
            self._last_attribution = cached["attribution"]
            # Restore DataFrame with index
            df = pd.DataFrame(cached["data"])
            if "index" in cached:
                df.index = pd.DatetimeIndex(cached["index"])
            return df

        # Fetch from Yahoo Finance
        self.logger.info("Fetching bars", ticker=ticker, window=window, interval=interval)

        try:
            # Download data with yfinance
            stock = yf.Ticker(ticker)
            end_date = datetime.now()
            # Request a bit more data to account for weekends/holidays
            start_date = end_date - timedelta(days=window * 2)

            df = stock.history(
                start=start_date,
                end=end_date,
                interval=interval,
                auto_adjust=True,  # Use adjusted prices
                actions=False,  # Don't include dividends/splits
            )

            if df.empty:
                raise DataNotFoundError(
                    f"No data found for ticker {ticker}",
                    source=self.source,
                )

            # Trim to requested window
            df = df.tail(window)

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
                api_endpoint=f"/v8/finance/chart/{ticker}",
                ticker=ticker,
                window=window,
                interval=interval,
                rows_fetched=len(df),
            )

            # Cache the result
            self.cache.set(
                cache_key,
                {
                    "data": df.to_dict("records"),
                    "attribution": self._last_attribution,
                    "index": df.index.tolist(),
                },
                metadata={"ticker": ticker, "window": window},
            )

            self.logger.info(
                "Bars fetched successfully",
                ticker=ticker,
                rows=len(df),
                date_range=f"{df.index[0]} to {df.index[-1]}",
            )

            return df

        except DataNotFoundError:
            # Re-raise DataNotFoundError as-is (don't wrap it)
            raise
        except YFException as e:
            raise PriceDataError(
                f"Yahoo Finance error for {ticker}: {e}",
                source=self.source,
                original_error=e,
            ) from e
        except Exception as e:
            # Check if it's a rate limit (HTTP 429)
            if "429" in str(e) or "Too Many Requests" in str(e):
                raise RateLimitError(
                    f"Rate limit exceeded for {ticker}",
                    source=self.source,
                    original_error=e,
                ) from e

            raise PriceDataError(
                f"Failed to fetch bars for {ticker}: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def get_latest_price(self, ticker: str) -> dict[str, Any]:
        """Get the latest price for a ticker.

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with latest price data:
                - price: Latest closing price
                - timestamp: When the price was recorded
                - change: Price change from previous close
                - change_pct: Percentage change

        Raises:
            PriceDataError: If price cannot be fetched

        Example:
            >>> adapter = PriceAdapter()
            >>> price_data = adapter.get_latest_price("AAPL")
            >>> assert price_data["price"] > 0
        """
        # Check cache
        cache_key = f"latest_price:{ticker}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for latest price", ticker=ticker)
            self._last_attribution = cached["attribution"]
            price_data: dict[str, Any] = cached["data"]
            return price_data

        self.logger.info("Fetching latest price", ticker=ticker)

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or "regularMarketPrice" not in info:
                # Fallback to history
                hist = stock.history(period="1d")
                if hist.empty:
                    raise DataNotFoundError(
                        f"No price data found for {ticker}",
                        source=self.source,
                    )
                price = float(hist["Close"].iloc[-1])
                timestamp = hist.index[-1]
                change = 0.0
                change_pct = 0.0
            else:
                price = float(info["regularMarketPrice"])
                timestamp = datetime.fromtimestamp(info.get("regularMarketTime", time.time()))
                prev_close = float(info.get("previousClose", price))
                change = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close > 0 else 0.0

            price_data = {
                "price": price,
                "timestamp": (
                    timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
                ),
                "change": change,
                "change_pct": change_pct,
            }

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
                ticker=ticker,
            )

            # Cache with shorter TTL (5 minutes for latest price)
            self.cache.set(
                cache_key,
                {"data": price_data, "attribution": self._last_attribution},
                ttl_seconds=300,
                metadata={"ticker": ticker},
            )

            self.logger.info("Latest price fetched", ticker=ticker, price=price)

            return price_data

        except (YFException, KeyError, ValueError, IndexError) as e:
            raise PriceDataError(
                f"Failed to fetch latest price for {ticker}: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def get_ticker_info(self, ticker: str) -> dict[str, Any]:
        """Get ticker information (market cap, sector, etc.).

        Args:
            ticker: Stock ticker symbol

        Returns:
            Dictionary with ticker information:
                - market_cap: Market capitalization
                - sector: Business sector
                - industry: Industry classification
                - avg_volume: Average trading volume
                - name: Company name

        Raises:
            PriceDataError: If info cannot be fetched

        Example:
            >>> adapter = PriceAdapter()
            >>> info = adapter.get_ticker_info("AAPL")
            >>> assert "market_cap" in info
        """
        # Check cache
        cache_key = f"ticker_info:{ticker}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for ticker info", ticker=ticker)
            self._last_attribution = cached["attribution"]
            info_data: dict[str, Any] = cached["data"]
            return info_data

        self.logger.info("Fetching ticker info", ticker=ticker)

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or "symbol" not in info or info.get("symbol") is None:
                raise DataNotFoundError(
                    f"No info found for ticker {ticker}",
                    source=self.source,
                )

            ticker_info = {
                "market_cap": info.get("marketCap", 0),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "avg_volume": info.get("averageVolume", 0),
                "name": info.get("longName") or info.get("shortName", ticker),
            }

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker}",
                ticker=ticker,
            )

            # Cache with longer TTL (1 day for ticker info)
            self.cache.set(
                cache_key,
                {"data": ticker_info, "attribution": self._last_attribution},
                ttl_seconds=86400,
                metadata={"ticker": ticker},
            )

            self.logger.info(
                "Ticker info fetched",
                ticker=ticker,
                market_cap=ticker_info["market_cap"],
                sector=ticker_info["sector"],
            )

            return ticker_info

        except DataNotFoundError:
            # Re-raise DataNotFoundError as-is
            raise
        except (YFException, KeyError, ValueError) as e:
            raise PriceDataError(
                f"Failed to fetch ticker info for {ticker}: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Generic fetch method (delegates to specific methods).

        This implements the DataAdapterProtocol interface.
        Use specific methods (get_bars, get_latest_price, etc.) instead.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Fetched data

        Raises:
            NotImplementedError: Use specific methods instead
        """
        raise NotImplementedError(
            "Use specific methods: get_bars(), get_latest_price(), get_ticker_info()"
        )

    def _build_attribution(self, **metadata: Any) -> Attribution:
        """Build attribution for fetched data.

        Args:
            **metadata: Additional metadata for attribution

        Returns:
            Attribution instance with source and metadata
        """
        return create_attribution(
            source=self.source,
            version="1.0",
            **metadata,
        )
