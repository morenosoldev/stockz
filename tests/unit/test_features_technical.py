"""
Tests for technical indicator calculations.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.technical import (
    InsufficientDataError,
    TechnicalIndicatorError,
    calculate_atr,
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    detect_bollinger_squeeze,
    is_overbought,
    is_oversold,
    price_vs_bands,
)


class TestATR:
    """Tests for ATR calculation."""

    def test_atr_basic_calculation(self):
        """Test basic ATR calculation."""
        data = pd.DataFrame(
            {
                "high": [102, 104, 103, 105, 107],
                "low": [98, 100, 99, 101, 103],
                "close": [100, 102, 101, 103, 105],
            }
        )
        atr = calculate_atr(data, period=3)

        # ATR should be positive
        assert atr.iloc[-1] > 0
        # ATR should increase with volatility
        assert not atr.isna().all()

    def test_atr_with_gaps(self):
        """Test ATR with price gaps."""
        data = pd.DataFrame(
            {
                "high": [100, 105, 110, 115, 120],  # Trending up with gaps
                "low": [95, 100, 105, 110, 115],
                "close": [98, 103, 108, 113, 118],
            }
        )
        atr = calculate_atr(data, period=3)

        # ATR should capture gap volatility
        assert atr.iloc[-1] > 0

    def test_atr_insufficient_data(self):
        """Test ATR with insufficient data."""
        data = pd.DataFrame(
            {
                "high": [100, 102],
                "low": [98, 99],
                "close": [99, 101],
            }
        )

        with pytest.raises(InsufficientDataError):
            calculate_atr(data, period=14)

    def test_atr_missing_columns(self):
        """Test ATR with missing columns."""
        data = pd.DataFrame({"close": [100, 102, 104]})

        with pytest.raises(TechnicalIndicatorError):
            calculate_atr(data, period=3)

    def test_atr_custom_columns(self):
        """Test ATR with custom column names."""
        data = pd.DataFrame(
            {
                "High": [102, 104, 103, 105],
                "Low": [98, 100, 99, 101],
                "Close": [100, 102, 101, 103],
            }
        )
        atr = calculate_atr(data, period=2, high_col="High", low_col="Low", close_col="Close")

        assert atr.iloc[-1] > 0


class TestRSI:
    """Tests for RSI calculation."""

    def test_rsi_basic_calculation(self):
        """Test basic RSI calculation."""
        # Create trending up data
        data = pd.DataFrame({"close": [100, 102, 104, 106, 108, 110, 112, 114, 116, 118] * 2})
        rsi = calculate_rsi(data, period=5)

        # RSI should be between 0 and 100
        assert (rsi >= 0).all()
        assert (rsi <= 100).all()
        # Trending up should have high RSI
        assert rsi.iloc[-1] > 50

    def test_rsi_trending_down(self):
        """Test RSI with trending down prices."""
        data = pd.DataFrame({"close": [120, 118, 116, 114, 112, 110, 108, 106, 104, 102] * 2})
        rsi = calculate_rsi(data, period=5)

        # Trending down should have low RSI
        assert rsi.iloc[-1] < 50

    def test_rsi_sideways(self):
        """Test RSI with sideways/choppy prices."""
        data = pd.DataFrame({"close": [100, 101, 100, 101, 100, 101, 100, 101, 100, 101] * 2})
        rsi = calculate_rsi(data, period=5)

        # Sideways should have RSI near 50 (allow wider range due to calculation method)
        assert 35 < rsi.iloc[-1] < 65

    def test_rsi_insufficient_data(self):
        """Test RSI with insufficient data."""
        data = pd.DataFrame({"close": [100, 102]})

        with pytest.raises(InsufficientDataError):
            calculate_rsi(data, period=14)

    def test_rsi_missing_column(self):
        """Test RSI with missing column."""
        data = pd.DataFrame({"high": [100, 102, 104]})

        with pytest.raises(TechnicalIndicatorError):
            calculate_rsi(data)

    def test_rsi_all_gains(self):
        """Test RSI with all gains (no losses)."""
        data = pd.DataFrame({"close": list(range(100, 120))})
        rsi = calculate_rsi(data, period=5)

        # All gains should result in RSI near 100
        assert rsi.iloc[-1] > 80

    def test_is_oversold_helper(self):
        """Test is_oversold helper function."""
        assert is_oversold(25.0) is True
        assert is_oversold(30.0) is False  # At threshold
        assert is_oversold(50.0) is False

    def test_is_overbought_helper(self):
        """Test is_overbought helper function."""
        assert is_overbought(75.0) is True
        assert is_overbought(70.0) is False  # At threshold
        assert is_overbought(50.0) is False


class TestSMA:
    """Tests for SMA calculation."""

    def test_sma_basic_calculation(self):
        """Test basic SMA calculation."""
        data = pd.DataFrame({"close": [100, 102, 104, 106, 108]})
        sma = calculate_sma(data, period=3)

        # Last SMA should be average of last 3 values
        expected = (104 + 106 + 108) / 3
        assert abs(sma.iloc[-1] - expected) < 0.01

    def test_sma_all_same_values(self):
        """Test SMA with constant prices."""
        data = pd.DataFrame({"close": [100] * 10})
        sma = calculate_sma(data, period=5)

        # SMA of constant should equal the constant
        assert sma.iloc[-1] == 100

    def test_sma_insufficient_data(self):
        """Test SMA with insufficient data."""
        data = pd.DataFrame({"close": [100, 102]})

        with pytest.raises(InsufficientDataError):
            calculate_sma(data, period=5)

    def test_sma_missing_column(self):
        """Test SMA with missing column."""
        data = pd.DataFrame({"high": [100, 102, 104]})

        with pytest.raises(TechnicalIndicatorError):
            calculate_sma(data, period=3, price_col="close")

    def test_sma_custom_column(self):
        """Test SMA with custom column name."""
        data = pd.DataFrame({"price": [100, 102, 104, 106, 108]})
        sma = calculate_sma(data, period=3, price_col="price")

        expected = (104 + 106 + 108) / 3
        assert abs(sma.iloc[-1] - expected) < 0.01


class TestEMA:
    """Tests for EMA calculation."""

    def test_ema_basic_calculation(self):
        """Test basic EMA calculation."""
        data = pd.DataFrame({"close": [100, 102, 104, 106, 108]})
        ema = calculate_ema(data, period=3)

        # EMA should give more weight to recent prices
        assert ema.iloc[-1] > 0
        # EMA should be closer to recent prices than SMA
        sma = calculate_sma(data, period=3)
        assert ema.iloc[-1] >= sma.iloc[-1]  # In uptrend, EMA > SMA

    def test_ema_vs_sma_trending_up(self):
        """Test EMA vs SMA in uptrend."""
        data = pd.DataFrame({"close": list(range(100, 120))})
        ema = calculate_ema(data, period=5)
        sma = calculate_sma(data, period=5)

        # In uptrend, EMA should be above SMA (more responsive)
        assert ema.iloc[-1] > sma.iloc[-1]

    def test_ema_vs_sma_trending_down(self):
        """Test EMA vs SMA in downtrend."""
        data = pd.DataFrame({"close": list(range(120, 100, -1))})
        ema = calculate_ema(data, period=5)
        sma = calculate_sma(data, period=5)

        # In downtrend, EMA should be below SMA (more responsive)
        assert ema.iloc[-1] < sma.iloc[-1]

    def test_ema_insufficient_data(self):
        """Test EMA with insufficient data."""
        data = pd.DataFrame({"close": [100, 102]})

        with pytest.raises(InsufficientDataError):
            calculate_ema(data, period=5)


class TestBollingerBands:
    """Tests for Bollinger Bands calculation."""

    def test_bollinger_bands_basic(self):
        """Test basic Bollinger Bands calculation."""
        data = pd.DataFrame({"close": list(range(100, 125))})
        bb = calculate_bollinger_bands(data, period=10)

        # Should have all required columns
        assert "middle" in bb.columns
        assert "upper" in bb.columns
        assert "lower" in bb.columns
        assert "percent_b" in bb.columns
        assert "bandwidth" in bb.columns

        # Upper should be above middle, lower should be below (excluding NaN rows)
        valid_rows = bb[~bb["middle"].isna()]
        assert (valid_rows["upper"] >= valid_rows["middle"]).all()
        assert (valid_rows["lower"] <= valid_rows["middle"]).all()

    def test_bollinger_bands_no_volatility(self):
        """Test Bollinger Bands with no volatility."""
        data = pd.DataFrame({"close": [100] * 25})
        bb = calculate_bollinger_bands(data, period=20)

        # With no volatility, bands should collapse to middle
        # (bandwidth should be very small or NaN)
        assert bb["bandwidth"].iloc[-1] < 0.01 or pd.isna(bb["bandwidth"].iloc[-1])

    def test_bollinger_bands_high_volatility(self):
        """Test Bollinger Bands with high volatility."""
        # Create highly volatile data
        np.random.seed(42)
        data = pd.DataFrame({"close": 100 + np.random.randn(30) * 10})
        bb = calculate_bollinger_bands(data, period=20)

        # High volatility should result in wide bands
        assert bb["bandwidth"].iloc[-1] > 0.1

    def test_bollinger_bands_percent_b(self):
        """Test %B calculation."""
        data = pd.DataFrame({"close": list(range(100, 125))})
        bb = calculate_bollinger_bands(data, period=10)

        # %B should be between 0 and 1 for prices within bands
        # (can be <0 or >1 for prices outside bands)
        assert not bb["percent_b"].isna().all()

    def test_bollinger_bands_insufficient_data(self):
        """Test Bollinger Bands with insufficient data."""
        data = pd.DataFrame({"close": [100, 102, 104]})

        with pytest.raises(InsufficientDataError):
            calculate_bollinger_bands(data, period=20)

    def test_bollinger_bands_custom_std(self):
        """Test Bollinger Bands with custom standard deviation."""
        data = pd.DataFrame({"close": list(range(100, 125))})
        bb_2std = calculate_bollinger_bands(data, period=10, num_std=2.0)
        bb_3std = calculate_bollinger_bands(data, period=10, num_std=3.0)

        # 3 std bands should be wider than 2 std bands
        assert bb_3std["bandwidth"].iloc[-1] > bb_2std["bandwidth"].iloc[-1]

    def test_detect_bollinger_squeeze(self):
        """Test Bollinger Band squeeze detection."""
        # Low volatility data
        data = pd.DataFrame({"close": [100 + i * 0.1 for i in range(25)]})
        bb = calculate_bollinger_bands(data, period=20)
        squeeze = detect_bollinger_squeeze(bb, threshold=0.05)

        # Low volatility should trigger squeeze
        assert squeeze.iloc[-1]

    def test_price_vs_bands_above(self):
        """Test price position vs bands - above."""
        data = pd.DataFrame({"close": [100] * 20 + [120]})  # Price spike
        bb = calculate_bollinger_bands(data, period=20)
        position = price_vs_bands(120, bb.iloc[-1:])

        assert position == "above_upper"

    def test_price_vs_bands_below(self):
        """Test price position vs bands - below."""
        data = pd.DataFrame({"close": [100] * 20 + [80]})  # Price drop
        bb = calculate_bollinger_bands(data, period=20)
        position = price_vs_bands(80, bb.iloc[-1:])

        assert position == "below_lower"

    def test_price_vs_bands_within(self):
        """Test price position vs bands - within."""
        data = pd.DataFrame({"close": [100] * 21})
        bb = calculate_bollinger_bands(data, period=20)
        position = price_vs_bands(100, bb.iloc[-1:])

        assert position == "in_bands"


class TestMACD:
    """Tests for MACD calculation."""

    def test_macd_basic_calculation(self):
        """Test basic MACD calculation."""
        data = pd.DataFrame({"close": list(range(100, 150))})
        macd = calculate_macd(data)

        # Should have all required columns
        assert "macd" in macd.columns
        assert "signal" in macd.columns
        assert "histogram" in macd.columns

        # Histogram should be MACD - Signal
        expected_hist = macd["macd"] - macd["signal"]
        assert abs((macd["histogram"] - expected_hist).sum()) < 0.01

    def test_macd_trending_up(self):
        """Test MACD in uptrend."""
        data = pd.DataFrame({"close": list(range(100, 150))})
        macd = calculate_macd(data)

        # In strong uptrend, MACD should be positive
        assert macd["macd"].iloc[-1] > 0

    def test_macd_trending_down(self):
        """Test MACD in downtrend."""
        data = pd.DataFrame({"close": list(range(150, 100, -1))})
        macd = calculate_macd(data)

        # In strong downtrend, MACD should be negative
        assert macd["macd"].iloc[-1] < 0

    def test_macd_crossover(self):
        """Test MACD crossover detection."""
        # Create data that will cause crossover
        data = pd.DataFrame({"close": list(range(100, 120)) + list(range(120, 140))})
        macd = calculate_macd(data)

        # Check that histogram changes sign (crossover)
        hist_signs = np.sign(macd["histogram"].dropna())
        has_crossover = len(hist_signs.unique()) > 1
        assert has_crossover

    def test_macd_insufficient_data(self):
        """Test MACD with insufficient data."""
        data = pd.DataFrame({"close": list(range(100, 110))})

        with pytest.raises(InsufficientDataError):
            calculate_macd(data)  # Needs at least 26 + 9 = 35 periods

    def test_macd_custom_periods(self):
        """Test MACD with custom periods."""
        data = pd.DataFrame({"close": list(range(100, 150))})
        macd_default = calculate_macd(data)
        macd_custom = calculate_macd(data, fast_period=8, slow_period=17, signal_period=5)

        # Custom periods should give different results
        assert macd_default["macd"].iloc[-1] != macd_custom["macd"].iloc[-1]


class TestRealWorldData:
    """Tests with realistic market data patterns."""

    def test_all_indicators_on_real_pattern(self):
        """Test all indicators together on realistic pattern."""
        # Create realistic price pattern: sideways, drop, recovery
        np.random.seed(42)
        sideways = [100 + np.random.randn() for _ in range(20)]
        drop = [sideways[-1] - i * 2 for i in range(10)]
        recovery = [drop[-1] + i * 1.5 for i in range(15)]

        data = pd.DataFrame(
            {
                "high": [p + 1 for p in sideways + drop + recovery],
                "low": [p - 1 for p in sideways + drop + recovery],
                "close": sideways + drop + recovery,
            }
        )

        # Calculate all indicators
        atr = calculate_atr(data, period=14)
        rsi = calculate_rsi(data, period=14)
        sma_20 = calculate_sma(data, period=20)
        ema_12 = calculate_ema(data, period=12)
        bb = calculate_bollinger_bands(data, period=20)
        macd = calculate_macd(data)

        # All should produce valid results
        assert not atr.isna().all()
        assert not rsi.isna().all()
        assert not sma_20.isna().all()
        assert not ema_12.isna().all()
        assert not bb["middle"].isna().all()
        assert not macd["macd"].isna().all()

        # After drop, RSI should be low
        drop_rsi = rsi.iloc[25:30].mean()  # During drop period
        assert drop_rsi < 50

        # After recovery, RSI should increase
        recovery_rsi = rsi.iloc[-5:].mean()
        assert recovery_rsi > drop_rsi

    def test_indicators_with_gaps(self):
        """Test indicators handle price gaps correctly."""
        # Create data with gap up
        data = pd.DataFrame(
            {
                "high": [100, 101, 102, 110, 111, 112],  # Gap from 102 to 110
                "low": [99, 100, 101, 109, 110, 111],
                "close": [100, 101, 102, 110, 111, 112],
            }
        )

        # ATR should capture the gap
        atr = calculate_atr(data, period=3)
        assert atr.iloc[-1] > 1  # Should reflect increased volatility

    def test_indicators_with_low_prices(self):
        """Test indicators work with low absolute prices."""
        data = pd.DataFrame(
            {
                "high": [1.05, 1.10, 1.08, 1.12, 1.15],
                "low": [0.95, 1.00, 0.98, 1.02, 1.05],
                "close": [1.00, 1.05, 1.03, 1.07, 1.10],
            }
        )

        # All indicators should work
        atr = calculate_atr(data, period=3)
        rsi = calculate_rsi(data, period=3)

        assert atr.iloc[-1] > 0
        assert 0 <= rsi.iloc[-1] <= 100
