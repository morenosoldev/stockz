"""Yahoo Finance fallback adapter for market data.

This adapter provides a temporary fallback to yfinance during the migration period.
It implements the same MarketDataProtocol interface for seamless switching.

WARNING: yfinance is unreliable and will be removed after 2 weeks of stable Twelve Data operation.
"""

import logging
from datetime import date, datetime

import pandas as pd
import yfinance as yf

from .attribution import Attribution, DataSource
from .market_data import (
    MarketDataProvider,
    OHLCVBar,
    TickerInfo,
)

logger = logging.getLogger(__name__)


class YFinanceFallbackAdapter:
    """Yahoo Finance adapter implementing MarketDataProtocol.

    This is a temporary fallback adapter during migration to Twelve Data.
    Will be removed after 2 weeks of stable Twelve Data operation.

    Note: yfinance is unreliable and frequently breaks. Use only as emergency fallback.
    """

    def __init__(self) -> None:
        """Initialize Yahoo Finance fallback adapter."""
        self._last_attribution: Attribution | None = None
        logger.warning(
            "YFinanceFallbackAdapter initialized. "
            "This is a temporary fallback and should not be used long-term."
        )

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return MarketDataProvider.YAHOO_FINANCE.value

    @property
    def data_source(self) -> DataSource:
        """Return DataSource for attribution."""
        return DataSource.YAHOO_FINANCE

    def _create_attribution(self, operation: str) -> Attribution:
        """Create attribution metadata.

        Args:
            operation: Operation performed (e.g., 'get_ohlcv', 'validate_ticker')

        Returns:
            Attribution object
        """
        attribution = Attribution(
            source=self.data_source,
            timestamp=datetime.now(),
            url="https://query1.finance.yahoo.com",
            api_endpoint=f"/yfinance/{operation}",
            version="1.0",
            metadata={"provider": self.provider_name, "fallback": True},
        )
        self._last_attribution = attribution
        return attribution

    def get_ohlcv(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        interval: str = "1d",
        limit: int | None = None,
    ) -> list[OHLCVBar]:
        """Fetch OHLCV data from Yahoo Finance.

        Args:
            ticker: Stock ticker symbol
            start_date: Start date (optional)
            end_date: End date (optional)
            interval: Time interval (1d, 1wk, 1mo)
            limit: Maximum bars to return (applied after fetch)

        Returns:
            List of OHLCVBar objects with attribution

        Raises:
            ValueError: If ticker is invalid
            Exception: If yfinance fails
        """
        logger.info(f"[FALLBACK] Fetching OHLCV for {ticker} from Yahoo Finance")

        try:
            # Create yfinance Ticker object
            stock = yf.Ticker(ticker)

            # Fetch history
            if start_date and end_date:
                df = stock.history(start=start_date, end=end_date, interval=interval)
            elif start_date:
                df = stock.history(start=start_date, interval=interval)
            elif end_date:
                df = stock.history(end=end_date, interval=interval)
            else:
                # Default to 1 year of data
                df = stock.history(period="1y", interval=interval)

            if df.empty:
                logger.warning(f"[FALLBACK] No data returned for {ticker}")
                return []

            # Apply limit if specified
            if limit:
                df = df.tail(limit)

            # Create attribution
            attribution = self._create_attribution("get_ohlcv")

            # Convert to OHLCVBar objects
            bars: list[OHLCVBar] = []
            for timestamp, row in df.iterrows():
                bar = OHLCVBar(
                    timestamp=pd.to_datetime(timestamp),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]),
                    attribution=attribution,
                )
                bars.append(bar)

            logger.info(f"[FALLBACK] Fetched {len(bars)} bars for {ticker}")
            return bars

        except Exception as e:
            logger.error(f"[FALLBACK] Failed to fetch OHLCV for {ticker}: {e}")
            raise

    def validate_ticker(self, ticker: str) -> bool:
        """Validate ticker using yfinance.

        Args:
            ticker: Ticker symbol to validate

        Returns:
            True if ticker exists, False otherwise
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            # Check if we got valid data back
            return bool(info and "symbol" in info)
        except Exception as e:
            logger.error(f"[FALLBACK] Ticker validation failed for {ticker}: {e}")
            return False

    def get_ticker_info(self, ticker: str) -> TickerInfo | None:
        """Get ticker information from yfinance.

        Args:
            ticker: Ticker symbol

        Returns:
            TickerInfo object or None if not found
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            if not info or "symbol" not in info:
                return None

            attribution = self._create_attribution("get_ticker_info")

            return TickerInfo(
                symbol=info.get("symbol", ticker),
                name=info.get("longName") or info.get("shortName"),
                exchange=info.get("exchange"),
                currency=info.get("currency"),
                country=info.get("country"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                market_cap=info.get("marketCap"),
                attribution=attribution,
            )
        except Exception as e:
            logger.error(f"[FALLBACK] Failed to get ticker info for {ticker}: {e}")
            return None

    def search_symbol(self, query: str, limit: int = 10) -> list[TickerInfo]:
        """Search for symbols.

        Note: yfinance doesn't support symbol search, so this returns empty list.

        Args:
            query: Search query
            limit: Max results (ignored)

        Returns:
            Empty list (yfinance doesn't support search)
        """
        logger.warning("[FALLBACK] Symbol search not supported by yfinance")
        return []

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
                metadata={"fallback": True},
            )
        return self._last_attribution

    def health_check(self) -> bool:
        """Check yfinance health.

        Returns:
            True if yfinance is accessible, False otherwise
        """
        try:
            bars = self.get_ohlcv("AAPL", limit=1)
            return len(bars) > 0
        except Exception as e:
            logger.error(f"[FALLBACK] Health check failed: {e}")
            return False
