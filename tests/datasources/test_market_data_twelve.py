"""Unit tests for Twelve Data adapter."""

from datetime import date, datetime
from unittest.mock import patch

import pandas as pd
import pytest

from src.datasources.base import DataSource
from src.datasources.market_data import OHLCVBar, TickerInfo
from src.datasources.market_data_twelve import TwelveDataAdapter


class TestTwelveDataAdapter:
    """Test suite for TwelveDataAdapter."""

    @pytest.fixture
    def adapter(self):
        """Create adapter instance for testing."""
        return TwelveDataAdapter(
            api_key="test_api_key",
            rate_limit_calls_per_minute=8,
            cache_ttl_seconds=3600,
        )

    @pytest.fixture
    def mock_ohlcv_response(self):
        """Mock OHLCV DataFrame response."""
        data = {
            "open": [100.0, 101.0, 102.0],
            "high": [105.0, 106.0, 107.0],
            "low": [99.0, 100.0, 101.0],
            "close": [104.0, 105.0, 106.0],
            "volume": [1000000, 1100000, 1200000],
        }
        index = pd.date_range(start="2025-01-01", periods=3, freq="D")
        return pd.DataFrame(data, index=index)

    def test_initialization(self, adapter):
        """Test adapter initializes correctly."""
        assert adapter.api_key == "test_api_key"
        assert adapter.rate_limit_calls_per_minute == 8
        assert adapter.cache_ttl_seconds == 3600
        assert adapter.provider_name == "twelve_data"
        assert adapter.data_source == DataSource.TWELVE_DATA

    def test_get_ohlcv_success(self, adapter, mock_ohlcv_response):
        """Test successful OHLCV data fetch."""
        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.return_value = mock_ohlcv_response

            bars = adapter.get_ohlcv("AAPL", limit=3)

            assert len(bars) == 3
            assert isinstance(bars[0], OHLCVBar)
            assert bars[0].open == 100.0
            assert bars[0].high == 105.0
            assert bars[0].low == 99.0
            assert bars[0].close == 104.0
            assert bars[0].volume == 1000000
            assert bars[0].attribution.source == DataSource.TWELVE_DATA

    def test_get_ohlcv_with_date_range(self, adapter, mock_ohlcv_response):
        """Test OHLCV fetch with date range."""
        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.return_value = mock_ohlcv_response

            start = date(2025, 1, 1)
            end = date(2025, 1, 3)
            bars = adapter.get_ohlcv("AAPL", start_date=start, end_date=end)

            assert len(bars) == 3
            mock_ts.assert_called_once()

    def test_get_ohlcv_caching(self, adapter, mock_ohlcv_response):
        """Test that OHLCV results are cached."""
        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.return_value = mock_ohlcv_response

            # First call - should hit API
            bars1 = adapter.get_ohlcv("AAPL", limit=3)
            assert mock_ts.call_count == 1

            # Second call - should use cache
            bars2 = adapter.get_ohlcv("AAPL", limit=3)
            assert mock_ts.call_count == 1  # Still 1, not 2

            assert len(bars1) == len(bars2)

    def test_validate_ticker_success(self, adapter):
        """Test successful ticker validation."""
        mock_search_result = {
            "symbol": "AAPL",
            "instrument_name": "Apple Inc.",
        }

        with patch.object(adapter.client, "symbol_search") as mock_search:
            mock_search.return_value.as_json.return_value = [mock_search_result]

            is_valid = adapter.validate_ticker("AAPL")

            assert is_valid is True

    def test_validate_ticker_not_found(self, adapter):
        """Test ticker validation for non-existent ticker."""
        with patch.object(adapter.client, "symbol_search") as mock_search:
            mock_search.return_value.as_json.return_value = []

            is_valid = adapter.validate_ticker("FAKESYMBOL")

            assert is_valid is False

    def test_get_ticker_info_success(self, adapter):
        """Test successful ticker info fetch."""
        mock_search_result = {
            "symbol": "AAPL",
            "instrument_name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "country": "United States",
        }

        with patch.object(adapter.client, "symbol_search") as mock_search:
            mock_search.return_value.as_json.return_value = [mock_search_result]

            info = adapter.get_ticker_info("AAPL")

            assert info is not None
            assert isinstance(info, TickerInfo)
            assert info.symbol == "AAPL"
            assert info.name == "Apple Inc."
            assert info.exchange == "NASDAQ"
            assert info.currency == "USD"

    def test_search_symbol(self, adapter):
        """Test symbol search."""
        mock_results = [
            {"symbol": "AAPL", "instrument_name": "Apple Inc."},
            {"symbol": "APLT", "instrument_name": "Applied Therapeutics Inc."},
        ]

        with patch.object(adapter.client, "symbol_search") as mock_search:
            mock_search.return_value.as_json.return_value = mock_results

            results = adapter.search_symbol("APL", limit=2)

            assert len(results) == 2
            assert results[0].symbol == "AAPL"
            assert results[1].symbol == "APLT"

    def test_rate_limiting(self, adapter):
        """Test that rate limiting is enforced."""
        import time

        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_df = pd.DataFrame(
                {"open": [100], "high": [105], "low": [99], "close": [104], "volume": [1000000]},
                index=pd.date_range(start="2025-01-01", periods=1),
            )
            mock_ts.return_value.as_pandas.return_value = mock_df

            start = time.time()

            # Make two calls
            adapter.get_ohlcv("AAPL", limit=1)
            adapter.cache.clear()  # Clear cache to force second API call
            adapter.get_ohlcv("AAPL", limit=1)

            elapsed = time.time() - start

            # Should take at least rate_limit_delay seconds (7.5s for 8/min)
            assert elapsed >= adapter.rate_limit_delay

    def test_health_check_success(self, adapter):
        """Test successful health check."""
        mock_df = pd.DataFrame(
            {"open": [100], "high": [105], "low": [99], "close": [104], "volume": [1000000]},
            index=pd.date_range(start="2025-01-01", periods=1),
        )

        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.return_value = mock_df

            result = adapter.health_check()

            assert result is True

    def test_health_check_failure(self, adapter):
        """Test health check failure."""
        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.side_effect = Exception("API Error")

            result = adapter.health_check()

            assert result is False

    def test_attribution_tracking(self, adapter, mock_ohlcv_response):
        """Test that attribution is properly tracked."""
        with patch.object(adapter.client, "time_series") as mock_ts:
            mock_ts.return_value.as_pandas.return_value = mock_ohlcv_response

            adapter.get_ohlcv("AAPL", limit=3)
            attribution = adapter.get_attribution()

            assert attribution.source == DataSource.TWELVE_DATA
            assert attribution.timestamp is not None
            assert isinstance(attribution.timestamp, datetime)
            assert attribution.url is not None
            assert "twelvedata.com" in attribution.url

    def test_retry_logic(self, adapter):
        """Test retry logic on API failures."""
        from twelvedata.exceptions import TwelveDataError

        with patch.object(adapter.client, "time_series") as mock_ts:
            # Fail twice, then succeed
            mock_ts.return_value.as_pandas.side_effect = [
                TwelveDataError("Temporary error"),
                TwelveDataError("Temporary error"),
                pd.DataFrame(
                    {
                        "open": [100],
                        "high": [105],
                        "low": [99],
                        "close": [104],
                        "volume": [1000000],
                    },
                    index=pd.date_range(start="2025-01-01", periods=1),
                ),
            ]

            bars = adapter.get_ohlcv("AAPL", limit=1)

            # Should succeed after retries
            assert len(bars) == 1
            assert mock_ts.call_count == 3  # Initial + 2 retries
