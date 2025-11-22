"""Twelve Data market data adapter with rate limiting and caching.

This adapter implements the MarketDataProtocol for Twelve Data API.
Features:
- Rate limiting (8 calls/min for Basic plan)
- Response caching (1 hour TTL)
- Automatic retries with exponential backoff
- Proper attribution for all data
"""

import logging
import time
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

import pandas as pd
from twelvedata import TDClient
from twelvedata.exceptions import TwelveDataError

from .attribution import Attribution, DataSource
from .cache import Cache
from .market_data import (
    MarketDataProvider,
    OHLCVBar,
    TickerInfo,
)

logger = logging.getLogger(__name__)


class TwelveDataAdapter:
    """Twelve Data API adapter with rate limiting and caching.

    Implements MarketDataProtocol for Twelve Data API access with:
    - Rate limiting: 8 calls/minute (Basic plan)
    - Caching: 1 hour TTL to reduce API usage
    - Retries: 3 attempts with exponential backoff
    - Attribution: Full source tracking for all data
    """

    def __init__(
        self,
        api_key: str,
        rate_limit_calls_per_minute: int = 8,
        cache_ttl_seconds: int = 3600,
        timeout_seconds: int = 30,
        retry_attempts: int = 3,
        retry_backoff: float = 2.0,
    ):
        """Initialize Twelve Data adapter.

        Args:
            api_key: Twelve Data API key
            rate_limit_calls_per_minute: Max API calls per minute (default: 8 for Basic plan)
            cache_ttl_seconds: Cache time-to-live in seconds (default: 3600 = 1 hour)
            timeout_seconds: API request timeout (default: 30)
            retry_attempts: Number of retry attempts on failure (default: 3)
            retry_backoff: Exponential backoff multiplier (default: 2.0)
        """
        self.api_key = api_key
        self.client = TDClient(apikey=api_key)
        self.rate_limit_calls_per_minute = rate_limit_calls_per_minute
        self.rate_limit_delay = 60.0 / rate_limit_calls_per_minute  # Seconds between calls
        self.cache_ttl_seconds = cache_ttl_seconds
        self.timeout_seconds = timeout_seconds
        self.retry_attempts = retry_attempts
        self.retry_backoff = retry_backoff

        # Rate limiting state
        self.last_call_time: float | None = None

        # Caching
        self.cache = Cache(ttl_seconds=cache_ttl_seconds)

        # Attribution tracking
        self._last_attribution: Attribution | None = None

        logger.info(
            f"Initialized TwelveDataAdapter: "
            f"rate_limit={rate_limit_calls_per_minute}/min, "
            f"cache_ttl={cache_ttl_seconds}s"
        )

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return MarketDataProvider.TWELVE_DATA.value

    @property
    def data_source(self) -> DataSource:
        """Return DataSource for attribution."""
        return DataSource.TWELVE_DATA

    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting between API calls."""
        if self.last_call_time is not None:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.rate_limit_delay:
                sleep_time = self.rate_limit_delay - elapsed
                logger.debug(f"Rate limit: sleeping {sleep_time:.2f}s")
                time.sleep(sleep_time)
        self.last_call_time = time.time()

    def _make_request_with_retry(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute API request with retry logic.

        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            TwelveDataError: If all retry attempts fail
        """
        last_error = None
        for attempt in range(self.retry_attempts):
            try:
                self._enforce_rate_limit()
                result = func(*args, **kwargs)
                return result
            except TwelveDataError as e:
                last_error = e
                if attempt < self.retry_attempts - 1:
                    backoff_time = self.retry_backoff**attempt
                    logger.warning(
                        f"API request failed (attempt {attempt + 1}/{self.retry_attempts}): {e}. "
                        f"Retrying in {backoff_time:.2f}s..."
                    )
                    time.sleep(backoff_time)
                else:
                    logger.error(f"API request failed after {self.retry_attempts} attempts: {e}")

        raise last_error  # type: ignore

    def _create_attribution(self, endpoint: str, params: dict[str, Any]) -> Attribution:
        """Create attribution metadata for API call.

        Args:
            endpoint: API endpoint called
            params: Request parameters

        Returns:
            Attribution object
        """
        attribution = Attribution(
            source=self.data_source,
            timestamp=datetime.now(),
            url=f"https://api.twelvedata.com/{endpoint}",
            api_endpoint=endpoint,
            version="1.0",
            metadata={"params": params, "provider": self.provider_name},
        )
        self._last_attribution = attribution
        return attribution

    def get_ohlcv(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: str = "1day",
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV data from Twelve Data.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (optional)
            end_date: End date (optional)
            interval: Time interval (1min, 5min, 15min, 30min, 45min, 1h, 2h, 4h, 8h, 1day, 1week, 1month)
            limit: Maximum bars to return (default: 5000 max for Twelve Data)

        Returns:
            List of OHLCVBar objects with attribution

        Raises:
            ValueError: If ticker is invalid
            TwelveDataError: If API request fails
        """
        # Normalize interval format (convert yfinance format to Twelve Data format)
        interval_map = {
            "1d": "1day",
            "1wk": "1week",
            "1mo": "1month",
            "1m": "1min",
            "5m": "5min",
            "15m": "15min",
            "30m": "30min",
            "1h": "1h",
        }
        interval = interval_map.get(interval, interval)
        # Build cache key
        cache_key = f"ohlcv_{ticker}_{start_date}_{end_date}_{interval}_{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {ticker} OHLCV data")
            return cached  # type: ignore[no-any-return]

        # Determine outputsize
        if limit:
            outputsize = min(limit, 5000)  # Twelve Data max
        else:
            outputsize = 5000

        # Build params
        params = {
            "symbol": ticker,
            "interval": interval,
            "outputsize": outputsize,
        }
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = end_date.strftime("%Y-%m-%d")

        logger.info(f"Fetching OHLCV for {ticker} (interval={interval}, outputsize={outputsize})")

        # Make API request
        def fetch() -> pd.DataFrame:
            ts = self.client.time_series(
                symbol=ticker,
                interval=interval,
                outputsize=outputsize,
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
            )
            result = ts.as_pandas()
            if not isinstance(result, pd.DataFrame):
                raise ValueError(f"Expected DataFrame from Twelve Data, got {type(result)}")
            return result

        df: pd.DataFrame = self._make_request_with_retry(fetch)

        # Create attribution
        attribution = self._create_attribution("time_series", params)

        # Convert to OHLCVBar objects
        bars: list[OHLCVBar] = []
        if df is not None and not df.empty:
            for timestamp, row in df.iterrows():
                bar = OHLCVBar(
                    timestamp=pd.to_datetime(str(timestamp)),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=int(row["volume"]),
                    attribution=attribution,
                )
                bars.append(bar)

        # Sort by timestamp (oldest first)
        bars.sort(key=lambda x: x.timestamp)

        # Cache result
        self.cache.set(cache_key, bars)

        logger.info(f"Fetched {len(bars)} bars for {ticker}")
        return bars

    def validate_ticker(self, ticker: str) -> bool:
        """Validate ticker by searching for it.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker exists, False otherwise
        """
        cache_key = f"validate_{ticker}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {ticker} validation")
            return bool(cached)

        try:
            results = self.search_symbol(ticker, limit=1)
            is_valid: bool = len(results) > 0 and results[0].symbol.upper() == ticker.upper()
            self.cache.set(cache_key, is_valid)
            return is_valid
        except Exception as e:
            logger.error(f"Ticker validation failed for {ticker}: {e}")
            return False

    def get_ticker_info(self, ticker: str) -> TickerInfo | None:
        """Get ticker information.

        Args:
            ticker: Ticker symbol

        Returns:
            TickerInfo object or None if not found
        """
        cache_key = f"info_{ticker}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for {ticker} info")
            return cached  # type: ignore[no-any-return]

        try:
            results = self.search_symbol(ticker, limit=1)
            if results and results[0].symbol.upper() == ticker.upper():
                info: TickerInfo = results[0]
                self.cache.set(cache_key, info)
                return info
            return None
        except Exception as e:
            logger.error(f"Failed to get ticker info for {ticker}: {e}")
            return None

    def search_symbol(self, query: str, limit: int = 10) -> list[TickerInfo]:
        """Search for symbols by name or ticker.

        Args:
            query: Search query
            limit: Max results

        Returns:
            List of TickerInfo objects
        """
        cache_key = f"search_{query}_{limit}"
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for symbol search: {query}")
            return cached  # type: ignore[no-any-return]

        logger.info(f"Searching symbols: {query}")

        def fetch() -> Any:
            return self.client.symbol_search(symbol=query).as_json()

        results: Any = self._make_request_with_retry(fetch)

        # Create attribution
        attribution = self._create_attribution("symbol_search", {"symbol": query})

        # Parse results
        ticker_infos: list[TickerInfo] = []
        data: list[dict[str, Any]] = (
            results if isinstance(results, list) else results.get("data", [])
        )

        for item in data[:limit]:
            info = TickerInfo(
                symbol=item.get("symbol", ""),
                name=item.get("instrument_name"),
                exchange=item.get("exchange"),
                currency=item.get("currency"),
                country=item.get("country"),
                attribution=attribution,
            )
            ticker_infos.append(info)

        # Cache results
        self.cache.set(cache_key, ticker_infos)

        logger.info(f"Found {len(ticker_infos)} symbols for query: {query}")
        return ticker_infos

    def get_attribution(self) -> Attribution:
        """Get attribution for last API call.

        Returns:
            Attribution object
        """
        if self._last_attribution is None:
            return Attribution(
                source=self.data_source,
                timestamp=datetime.now(),
                version="1.0",
            )
        return self._last_attribution

    def health_check(self) -> bool:
        """Check API health by fetching a known ticker.

        Returns:
            True if API is accessible, False otherwise
        """
        try:
            # Try fetching AAPL with minimal data
            bars = self.get_ohlcv("AAPL", interval="1d", limit=1)
            return len(bars) > 0
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
