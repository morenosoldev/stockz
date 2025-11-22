"""Integration test for technical analysis with Twelve Data.

This test verifies that the technical analysis adapter works correctly
with the Twelve Data market data adapter.
"""

from datetime import date

import pytest

from src.datasources import get_market_data_adapter
from src.datasources.technical import TechnicalDataAdapter


class TestTechnicalAnalysisIntegration:
    """Integration tests for technical analysis with Twelve Data."""

    @pytest.mark.integration
    def test_fetch_technical_data_aapl(self):
        """Test fetching technical data for AAPL using Twelve Data."""
        # Skip if no API key configured
        import os

        if not os.getenv("TWELVE_DATA_API_KEY"):
            pytest.skip("TWELVE_DATA_API_KEY not configured")

        adapter = TechnicalDataAdapter()
        today = date.today()

        # Fetch technical data
        tech_data = adapter.fetch_technical_data(ticker="AAPL", as_of_date=today, lookback_days=60)

        # Verify data structure
        assert tech_data.ticker == "AAPL"
        assert tech_data.as_of_date == today
        assert tech_data.current_price > 0

        # Verify trend indicators
        assert tech_data.sma_20 is not None
        assert tech_data.sma_50 is not None
        assert tech_data.ema_20 is not None

        # Verify momentum indicators
        assert tech_data.rsi is not None
        assert 0 <= tech_data.rsi <= 100

        # Verify volatility indicators
        assert tech_data.atr is not None
        assert tech_data.bb_upper is not None
        assert tech_data.bb_lower is not None

        # Verify volume indicators
        assert tech_data.volume is not None

        print("✓ AAPL technical data fetched successfully")
        print(f"  Current price: ${tech_data.current_price:.2f}")
        print(f"  RSI: {tech_data.rsi:.2f}")
        print(f"  ATR: ${tech_data.atr:.2f}")

    @pytest.mark.integration
    def test_market_data_adapter_direct(self):
        """Test market data adapter directly."""
        import os

        if not os.getenv("TWELVE_DATA_API_KEY"):
            pytest.skip("TWELVE_DATA_API_KEY not configured")

        # Get adapter
        adapter = get_market_data_adapter()

        # Fetch OHLCV data
        bars = adapter.get_ohlcv("AAPL", limit=5)

        assert len(bars) > 0
        assert bars[0].close > 0
        assert bars[0].volume > 0

        print(f"✓ Fetched {len(bars)} bars for AAPL")
        print(f"  Latest close: ${bars[-1].close:.2f}")
        print(f"  Latest volume: {bars[-1].volume:,}")

    @pytest.mark.integration
    def test_ticker_validation(self):
        """Test ticker validation using Twelve Data."""
        import os

        if not os.getenv("TWELVE_DATA_API_KEY"):
            pytest.skip("TWELVE_DATA_API_KEY not configured")

        adapter = get_market_data_adapter()

        # Valid ticker
        assert adapter.validate_ticker("AAPL") is True
        assert adapter.validate_ticker("MSFT") is True

        # Invalid ticker
        assert adapter.validate_ticker("FAKESYMBOL12345") is False

        print("✓ Ticker validation working correctly")
