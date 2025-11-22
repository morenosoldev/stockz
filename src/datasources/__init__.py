"""Data source adapters with attribution."""

import logging
import os
from typing import Any, Optional

from .market_data import MarketDataProtocol, MarketDataProvider, OHLCVBar, TickerInfo
from .market_data_twelve import TwelveDataAdapter
from .market_data_yfinance import YFinanceFallbackAdapter

__all__ = [
    "MarketDataProtocol",
    "MarketDataProvider",
    "OHLCVBar",
    "TickerInfo",
    "TwelveDataAdapter",
    "YFinanceFallbackAdapter",
    "get_market_data_adapter",
]

logger = logging.getLogger(__name__)


def get_market_data_adapter(
    provider: str | None = None,
    api_key: str | None = None,
    **kwargs: Any,
) -> MarketDataProtocol:
    """Factory function to get market data adapter.

    This function creates the appropriate market data adapter based on
    configuration. Defaults to Twelve Data, falls back to Yahoo Finance if needed.

    Args:
        provider: Provider name ('twelve_data', 'yahoo_finance'). Defaults to PRICE_DATA_PROVIDER env var.
        api_key: API key for the provider. Defaults to TWELVE_DATA_API_KEY env var for Twelve Data.
        **kwargs: Additional arguments passed to adapter constructor

    Returns:
        MarketDataProtocol instance (TwelveDataAdapter or YFinanceFallbackAdapter)

    Raises:
        ValueError: If provider is invalid or API key is missing

    Example:
        >>> # Get default adapter (from config)
        >>> adapter = get_market_data_adapter()
        >>>
        >>> # Get specific adapter
        >>> adapter = get_market_data_adapter(provider='twelve_data', api_key='your_key')
        >>>
        >>> # Fetch data
        >>> bars = adapter.get_ohlcv('AAPL', limit=10)
    """
    # Get provider from env or parameter
    if provider is None:
        provider = os.getenv("PRICE_DATA_PROVIDER", "twelve_data")

    provider = provider.lower()

    logger.info(f"Creating market data adapter: {provider}")

    if provider == MarketDataProvider.TWELVE_DATA.value:
        # Get API key from parameter or environment
        if api_key is None:
            api_key = os.getenv("TWELVE_DATA_API_KEY")

        if not api_key:
            raise ValueError(
                "Twelve Data API key is required. "
                "Set TWELVE_DATA_API_KEY environment variable or pass api_key parameter."
            )

        # Get configuration from environment or use defaults
        rate_limit = int(os.getenv("TWELVE_DATA_RATE_LIMIT_CALLS_PER_MINUTE", "8"))
        cache_ttl = int(os.getenv("CACHE_TTL_SECONDS", "3600"))
        timeout = int(os.getenv("TWELVE_DATA_TIMEOUT_SECONDS", "30"))
        retry_attempts = int(os.getenv("TWELVE_DATA_RETRY_ATTEMPTS", "3"))
        retry_backoff = float(os.getenv("TWELVE_DATA_RETRY_BACKOFF", "2.0"))

        adapter = TwelveDataAdapter(
            api_key=api_key,
            rate_limit_calls_per_minute=rate_limit,
            cache_ttl_seconds=cache_ttl,
            timeout_seconds=timeout,
            retry_attempts=retry_attempts,
            retry_backoff=retry_backoff,
            **kwargs,
        )

        logger.info("Initialized TwelveDataAdapter")
        return adapter

    elif provider == MarketDataProvider.YAHOO_FINANCE.value:
        logger.warning(
            "Using YFinanceFallbackAdapter. "
            "This is unreliable and should only be used as emergency fallback."
        )
        adapter_yf = YFinanceFallbackAdapter()
        return adapter_yf

    else:
        raise ValueError(
            f"Unknown market data provider: {provider}. "
            f"Supported: {[p.value for p in MarketDataProvider]}"
        )
