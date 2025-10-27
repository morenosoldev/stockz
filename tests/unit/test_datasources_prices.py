"""Tests for price data adapter with REAL API calls.

These tests make actual calls to Yahoo Finance API to ensure real-world functionality.
They may be slower than mocked tests but provide better confidence in the integration.
"""

import time

import pandas as pd
import pytest

from src.datasources.base import DataNotFoundError, DataSource
from src.datasources.cache import Cache
from src.datasources.prices import DEFAULT_UNIVERSE, PriceAdapter, PriceDataError


@pytest.fixture
def temp_cache(tmp_path):
    """Create a temporary cache for testing."""
    cache_dir = tmp_path / "test_cache"
    return Cache(cache_dir=cache_dir, ttl_seconds=300)


@pytest.fixture
def adapter(temp_cache):
    """Create a PriceAdapter with temporary cache."""
    return PriceAdapter(cache=temp_cache)


class TestPriceAdapterInitialization:
    """Test PriceAdapter initialization."""

    def test_create_adapter_with_cache(self, temp_cache):
        """Test creating adapter with provided cache."""
        adapter = PriceAdapter(cache=temp_cache)
        assert adapter.source == DataSource.YAHOO_FINANCE
        assert adapter.cache is temp_cache

    def test_create_adapter_without_cache(self):
        """Test creating adapter creates default cache."""
        adapter = PriceAdapter()
        assert adapter.source == DataSource.YAHOO_FINANCE
        assert adapter.cache is not None
        assert adapter.cache.ttl_seconds > 0


class TestGetUniverse:
    """Test get_universe method."""

    def test_get_universe_returns_list(self, adapter):
        """Test that get_universe returns a list of tickers."""
        universe = adapter.get_universe()
        assert isinstance(universe, list)
        assert len(universe) > 0

    def test_universe_contains_expected_tickers(self, adapter):
        """Test universe contains major tickers."""
        universe = adapter.get_universe()
        assert "AAPL" in universe
        assert "MSFT" in universe
        assert "GOOGL" in universe

    def test_universe_returns_copy(self, adapter):
        """Test that universe returns a copy (not reference to DEFAULT_UNIVERSE)."""
        universe1 = adapter.get_universe()
        universe2 = adapter.get_universe()
        assert universe1 == universe2
        assert universe1 is not universe2

    def test_universe_size_matches_default(self, adapter):
        """Test universe fetches S&P 500 tickers or falls back to DEFAULT_UNIVERSE."""
        universe = adapter.get_universe()
        # Should fetch S&P 500 (~500 tickers) or fall back to DEFAULT_UNIVERSE (28 tickers)
        assert len(universe) >= len(DEFAULT_UNIVERSE)
        assert len(universe) > 0


class TestGetBars:
    """Test get_bars method with real API calls."""

    def test_get_bars_aapl(self, adapter):
        """Test fetching bars for AAPL (real API call)."""
        bars = adapter.get_bars("AAPL", window=20)

        assert isinstance(bars, pd.DataFrame)
        assert len(bars) > 0
        assert len(bars) <= 20

        # Check expected columns
        assert "Open" in bars.columns
        assert "High" in bars.columns
        assert "Low" in bars.columns
        assert "Close" in bars.columns
        assert "Volume" in bars.columns

        # Check data types
        assert bars["Close"].dtype in ["float64", "float32"]
        assert bars["Volume"].dtype in ["int64", "int32"]

        # Verify prices are reasonable
        assert (bars["Close"] > 0).all()
        assert (bars["High"] >= bars["Low"]).all()

    def test_get_bars_multiple_tickers(self, adapter):
        """Test fetching bars for multiple tickers."""
        tickers = ["MSFT", "GOOGL", "AMZN"]

        for ticker in tickers:
            bars = adapter.get_bars(ticker, window=10)
            assert len(bars) > 0
            assert "Close" in bars.columns
            # Small delay to avoid rate limiting
            time.sleep(0.5)

    def test_get_bars_different_windows(self, adapter):
        """Test fetching different window sizes."""
        windows = [5, 10, 20]

        for window in windows:
            bars = adapter.get_bars("AAPL", window=window)
            assert len(bars) > 0
            assert len(bars) <= window

    def test_get_bars_caching(self, adapter):
        """Test that bars are cached on second call."""
        # First call - should fetch from API
        bars1 = adapter.get_bars("AAPL", window=20)

        # Second call - should use cache (faster)
        import time

        start = time.time()
        bars2 = adapter.get_bars("AAPL", window=20)
        elapsed = time.time() - start

        # Should be nearly instant from cache
        assert elapsed < 0.1
        assert len(bars2) == len(bars1)
        assert (bars2["Close"] == bars1["Close"]).all()

    def test_get_bars_invalid_ticker(self, adapter):
        """Test fetching bars for invalid ticker raises error."""
        with pytest.raises(DataNotFoundError):
            adapter.get_bars("INVALID_TICKER_XYZ", window=20)

    def test_get_bars_attribution(self, adapter):
        """Test that attribution is properly set."""
        adapter.get_bars("AAPL", window=20)
        attr = adapter.get_attribution()

        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.url is not None
        assert "AAPL" in attr.url
        assert attr.metadata.get("ticker") == "AAPL"
        assert attr.metadata.get("window") == 20

    def test_get_bars_returns_datetime_index(self, adapter):
        """Test that bars have DatetimeIndex."""
        bars = adapter.get_bars("AAPL", window=20)
        assert isinstance(bars.index, pd.DatetimeIndex)


class TestGetLatestPrice:
    """Test get_latest_price method with real API calls."""

    def test_get_latest_price_aapl(self, adapter):
        """Test fetching latest price for AAPL."""
        price_data = adapter.get_latest_price("AAPL")

        assert isinstance(price_data, dict)
        assert "price" in price_data
        assert "timestamp" in price_data
        assert "change" in price_data
        assert "change_pct" in price_data

        # Verify price is reasonable
        assert price_data["price"] > 0
        assert isinstance(price_data["price"], float)

    def test_get_latest_price_multiple_tickers(self, adapter):
        """Test fetching latest price for multiple tickers."""
        tickers = ["MSFT", "GOOGL"]

        for ticker in tickers:
            price_data = adapter.get_latest_price(ticker)
            assert price_data["price"] > 0
            time.sleep(0.5)

    def test_get_latest_price_caching(self, adapter):
        """Test that latest price is cached."""
        # First call
        price1 = adapter.get_latest_price("AAPL")

        # Second call - should be cached
        start = time.time()
        price2 = adapter.get_latest_price("AAPL")
        elapsed = time.time() - start

        # Should be nearly instant from cache
        assert elapsed < 0.1
        assert price2["price"] == price1["price"]

    def test_get_latest_price_invalid_ticker(self, adapter):
        """Test fetching price for invalid ticker raises error."""
        with pytest.raises((DataNotFoundError, PriceDataError)):
            adapter.get_latest_price("INVALID_TICKER_XYZ")

    def test_get_latest_price_attribution(self, adapter):
        """Test that attribution is properly set."""
        adapter.get_latest_price("AAPL")
        attr = adapter.get_attribution()

        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.url is not None
        assert "AAPL" in attr.url


class TestGetTickerInfo:
    """Test get_ticker_info method with real API calls."""

    def test_get_ticker_info_aapl(self, adapter):
        """Test fetching ticker info for AAPL."""
        info = adapter.get_ticker_info("AAPL")

        assert isinstance(info, dict)
        assert "market_cap" in info
        assert "sector" in info
        assert "industry" in info
        assert "avg_volume" in info
        assert "name" in info

        # Verify data is reasonable
        assert info["market_cap"] > 0
        assert info["sector"] != "Unknown"
        assert "Apple" in info["name"]

    def test_get_ticker_info_multiple_tickers(self, adapter):
        """Test fetching info for multiple tickers."""
        tickers = ["MSFT", "GOOGL"]

        for ticker in tickers:
            info = adapter.get_ticker_info(ticker)
            assert info["market_cap"] > 0
            assert info["sector"] != "Unknown"
            time.sleep(0.5)

    def test_get_ticker_info_caching(self, adapter):
        """Test that ticker info is cached."""
        # First call
        info1 = adapter.get_ticker_info("AAPL")

        # Second call - should be cached
        start = time.time()
        info2 = adapter.get_ticker_info("AAPL")
        elapsed = time.time() - start

        # Should be nearly instant from cache
        assert elapsed < 0.1
        assert info2["market_cap"] == info1["market_cap"]

    def test_get_ticker_info_invalid_ticker(self, adapter):
        """Test fetching info for invalid ticker raises error."""
        with pytest.raises((DataNotFoundError, PriceDataError)):
            adapter.get_ticker_info("INVALID_TICKER_XYZ")

    def test_get_ticker_info_attribution(self, adapter):
        """Test that attribution is properly set."""
        adapter.get_ticker_info("AAPL")
        attr = adapter.get_attribution()

        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.url is not None


class TestCacheIntegration:
    """Test cache integration."""

    def test_cache_keys_are_unique(self, adapter):
        """Test that different requests use different cache keys."""
        # Fetch with different parameters
        adapter.get_bars("AAPL", window=10)
        adapter.get_bars("AAPL", window=20)
        adapter.get_bars("MSFT", window=10)

        # Check cache has multiple entries
        stats = adapter.cache.get_stats()
        assert stats["total_entries"] >= 3

    def test_cache_persists_across_instances(self, temp_cache):
        """Test that cache persists across adapter instances."""
        # First adapter
        adapter1 = PriceAdapter(cache=temp_cache)
        bars1 = adapter1.get_bars("AAPL", window=20)

        # Second adapter with same cache
        adapter2 = PriceAdapter(cache=temp_cache)
        start = time.time()
        bars2 = adapter2.get_bars("AAPL", window=20)
        elapsed = time.time() - start

        # Should be instant from cache
        assert elapsed < 0.1
        assert len(bars2) == len(bars1)


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_ticker_raises_appropriate_error(self, adapter):
        """Test that invalid tickers raise DataNotFoundError."""
        with pytest.raises(DataNotFoundError):
            adapter.get_bars("NOT_A_REAL_TICKER_12345", window=20)

    def test_fetch_method_not_implemented(self, adapter):
        """Test that generic fetch() raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            adapter.fetch()


class TestRealWorldUsage:
    """Test real-world usage scenarios."""

    def test_scan_multiple_tickers_workflow(self, adapter):
        """Test a realistic workflow of scanning multiple tickers."""
        universe = adapter.get_universe()[:5]  # Just test first 5

        results = []
        for ticker in universe:
            try:
                # Get bars
                bars = adapter.get_bars(ticker, window=20)

                # Get latest price
                price_data = adapter.get_latest_price(ticker)

                # Get info
                info = adapter.get_ticker_info(ticker)

                results.append(
                    {
                        "ticker": ticker,
                        "bars_count": len(bars),
                        "latest_price": price_data["price"],
                        "market_cap": info["market_cap"],
                    }
                )

                # Be nice to the API
                time.sleep(0.5)

            except Exception as e:
                pytest.fail(f"Failed to fetch data for {ticker}: {e}")

        # Verify we got results for all tickers
        assert len(results) == 5
        for result in results:
            assert result["bars_count"] > 0
            assert result["latest_price"] > 0
            assert result["market_cap"] > 0

    def test_calculate_drop_from_bars(self, adapter):
        """Test calculating a price drop from bars (real strategy use case)."""
        bars = adapter.get_bars("AAPL", window=20)

        # Calculate drop from recent high
        recent_high = bars["High"].tail(10).max()
        current_close = bars["Close"].iloc[-1]
        drop_pct = ((current_close - recent_high) / recent_high) * 100

        # Drop should be a reasonable number
        assert -100 < drop_pct < 100

    def test_volume_analysis_from_bars(self, adapter):
        """Test volume analysis from bars (real strategy use case)."""
        bars = adapter.get_bars("AAPL", window=20)

        # Calculate average volume
        avg_volume = bars["Volume"].mean()
        current_volume = bars["Volume"].iloc[-1]

        # Volume ratio
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        # Should be a reasonable ratio
        assert volume_ratio >= 0
