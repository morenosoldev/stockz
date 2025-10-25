"""
Tests for price action feature engineering.

Tests cover gap detection, drop detection, reversals, and momentum calculations.
"""

import numpy as np
import pandas as pd
import pytest

from src.features.price_action import (
    InsufficientDataError,
    PriceActionError,
    calculate_avg_directional_change,
    calculate_price_momentum,
    calculate_true_range,
    detect_drop,
    detect_gap,
    detect_higher_low,
    detect_intraday_drop,
    detect_reversal_candle,
)


class TestDetectGap:
    """Tests for gap detection."""

    def test_gap_up(self):
        """Test detection of gap up."""
        df = pd.DataFrame({"open": [100, 105], "close": [102, 104]})
        gaps = detect_gap(df)

        # Gap from 102 (prev close) to 105 (today open) = 2.94%
        assert gaps.iloc[1] > 1.0

    def test_gap_down(self):
        """Test detection of gap down."""
        df = pd.DataFrame({"open": [100, 95], "close": [102, 96]})
        gaps = detect_gap(df)

        # Gap from 102 (prev close) to 95 (today open) = -6.86%
        assert gaps.iloc[1] < -1.0

    def test_no_gap(self):
        """Test no gap when prices are continuous."""
        df = pd.DataFrame({"open": [100, 102], "close": [102, 104]})
        gaps = detect_gap(df)

        # No gap (open == prev close)
        assert abs(gaps.iloc[1]) < 0.1

    def test_first_row_zero(self):
        """Test that first row has no gap."""
        df = pd.DataFrame({"open": [100, 105], "close": [102, 104]})
        gaps = detect_gap(df)

        assert gaps.iloc[0] == 0.0

    def test_missing_columns(self):
        """Test error when columns are missing."""
        df = pd.DataFrame({"open": [100, 105]})

        with pytest.raises(PriceActionError):
            detect_gap(df)

    def test_insufficient_data(self):
        """Test error when insufficient data."""
        df = pd.DataFrame({"open": [100], "close": [102]})

        with pytest.raises(InsufficientDataError):
            detect_gap(df)


class TestDetectDrop:
    """Tests for price drop detection."""

    def test_simple_drop(self):
        """Test detection of simple drop."""
        df = pd.DataFrame({"close": [100, 95]})
        drops = detect_drop(df, lookback=1)

        assert drops.iloc[-1] == -5.0

    def test_large_drop(self):
        """Test detection of large drop."""
        df = pd.DataFrame({"close": [100, 80]})
        drops = detect_drop(df, lookback=1)

        assert drops.iloc[-1] == -20.0

    def test_price_increase(self):
        """Test that price increase returns positive."""
        df = pd.DataFrame({"close": [100, 105]})
        drops = detect_drop(df, lookback=1)

        assert drops.iloc[-1] == 5.0

    def test_multi_period_lookback(self):
        """Test drop detection with longer lookback."""
        df = pd.DataFrame({"close": [100, 98, 96, 92]})
        drops = detect_drop(df, lookback=3)

        # Drop from 100 to 92 = -8%
        assert drops.iloc[-1] == -8.0

    def test_missing_column(self):
        """Test error when column is missing."""
        df = pd.DataFrame({"price": [100, 95]})

        with pytest.raises(PriceActionError):
            detect_drop(df)

    def test_insufficient_data(self):
        """Test error when insufficient data."""
        df = pd.DataFrame({"close": [100]})

        with pytest.raises(InsufficientDataError):
            detect_drop(df, lookback=1)


class TestDetectIntradayDrop:
    """Tests for intraday drop detection."""

    def test_drop_to_low(self):
        """Test intraday drop to low."""
        df = pd.DataFrame({"open": [100], "low": [92], "close": [98]})
        drops = detect_intraday_drop(df)

        # Drop from 100 to 92 = -8%
        assert drops.iloc[0] == -8.0

    def test_drop_to_close(self):
        """Test intraday drop to close."""
        df = pd.DataFrame({"open": [100], "low": [98], "close": [92]})
        drops = detect_intraday_drop(df)

        # Drop from 100 to 92 (close) = -8%
        assert drops.iloc[0] == -8.0

    def test_bullish_day(self):
        """Test bullish day (no drop)."""
        df = pd.DataFrame({"open": [100], "low": [99], "close": [105]})
        drops = detect_intraday_drop(df)

        # Minimum is low (-1%), not close (+5%)
        assert drops.iloc[0] == -1.0

    def test_missing_columns(self):
        """Test error when columns are missing."""
        df = pd.DataFrame({"open": [100], "close": [98]})

        with pytest.raises(PriceActionError):
            detect_intraday_drop(df)


class TestDetectReversalCandle:
    """Tests for reversal candle detection."""

    def test_hammer_pattern(self):
        """Test detection of hammer pattern."""
        df = pd.DataFrame(
            {
                "open": [95],
                "high": [98],
                "low": [90],
                "close": [97],
            }
        )
        reversals = detect_reversal_candle(df)

        # Long lower shadow, bullish close
        assert reversals.iloc[0]

    def test_not_bullish(self):
        """Test that bearish candle is not reversal."""
        df = pd.DataFrame(
            {
                "open": [97],
                "high": [98],
                "low": [90],
                "close": [95],
            }
        )
        reversals = detect_reversal_candle(df)

        # Bearish (close < open)
        assert not reversals.iloc[0]

    def test_no_long_shadow(self):
        """Test that candle without long shadow is not reversal."""
        df = pd.DataFrame(
            {
                "open": [95],
                "high": [98],
                "low": [94],
                "close": [97],
            }
        )
        reversals = detect_reversal_candle(df)

        # Lower shadow not long enough
        assert not reversals.iloc[0]

    def test_missing_columns(self):
        """Test error when columns are missing."""
        df = pd.DataFrame({"open": [100], "close": [102]})

        with pytest.raises(PriceActionError):
            detect_reversal_candle(df)


class TestCalculatePriceMomentum:
    """Tests for price momentum calculation."""

    def test_positive_momentum(self):
        """Test positive momentum."""
        df = pd.DataFrame({"close": [100, 105, 110, 115, 120, 125]})
        momentum = calculate_price_momentum(df, period=5)

        # Gain from 100 to 125 = 25%
        assert momentum.iloc[-1] == 25.0

    def test_negative_momentum(self):
        """Test negative momentum."""
        df = pd.DataFrame({"close": [125, 120, 115, 110, 105, 100]})
        momentum = calculate_price_momentum(df, period=5)

        # Loss from 125 to 100 = -20%
        assert momentum.iloc[-1] == -20.0

    def test_zero_momentum(self):
        """Test zero momentum (sideways)."""
        df = pd.DataFrame({"close": [100, 102, 98, 101, 99, 100]})
        momentum = calculate_price_momentum(df, period=5)

        # No net change from 100 to 100
        assert momentum.iloc[-1] == 0.0

    def test_missing_column(self):
        """Test error when column is missing."""
        df = pd.DataFrame({"price": [100, 105, 110]})

        with pytest.raises(PriceActionError):
            calculate_price_momentum(df)

    def test_insufficient_data(self):
        """Test error when insufficient data."""
        df = pd.DataFrame({"close": [100, 105]})

        with pytest.raises(InsufficientDataError):
            calculate_price_momentum(df, period=5)


class TestDetectHigherLow:
    """Tests for higher low detection."""

    def test_higher_low(self):
        """Test detection of higher low."""
        df = pd.DataFrame({"low": [90, 92, 94]})
        higher_lows = detect_higher_low(df, lookback=1)

        assert higher_lows.iloc[-1]

    def test_lower_low(self):
        """Test detection of lower low."""
        df = pd.DataFrame({"low": [94, 92, 90]})
        higher_lows = detect_higher_low(df, lookback=1)

        assert not higher_lows.iloc[-1]

    def test_equal_low(self):
        """Test equal low (not higher)."""
        df = pd.DataFrame({"low": [90, 90, 90]})
        higher_lows = detect_higher_low(df, lookback=1)

        assert not higher_lows.iloc[-1]

    def test_multi_period_lookback(self):
        """Test with longer lookback."""
        df = pd.DataFrame({"low": [85, 88, 90, 92, 94, 96]})
        higher_lows = detect_higher_low(df, lookback=5)

        # 96 > 85
        assert higher_lows.iloc[-1]

    def test_missing_column(self):
        """Test error when column is missing."""
        df = pd.DataFrame({"price": [100, 102]})

        with pytest.raises(PriceActionError):
            detect_higher_low(df)

    def test_insufficient_data(self):
        """Test error when insufficient data."""
        df = pd.DataFrame({"low": [90]})

        with pytest.raises(InsufficientDataError):
            detect_higher_low(df, lookback=1)


class TestCalculateTrueRange:
    """Tests for True Range calculation."""

    def test_simple_range(self):
        """Test simple H-L range (first row)."""
        df = pd.DataFrame({"high": [105], "low": [100], "close": [102]})
        tr = calculate_true_range(df)

        assert tr.iloc[0] == 5

    def test_with_gap_up(self):
        """Test True Range with gap up."""
        df = pd.DataFrame(
            {
                "high": [105, 115],
                "low": [100, 110],
                "close": [102, 112],
            }
        )
        tr = calculate_true_range(df)

        # max(115-110, 115-102, 110-102) = max(5, 13, 8) = 13
        assert tr.iloc[1] == 13

    def test_with_gap_down(self):
        """Test True Range with gap down."""
        df = pd.DataFrame(
            {
                "high": [105, 98],
                "low": [100, 93],
                "close": [102, 95],
            }
        )
        tr = calculate_true_range(df)

        # max(98-93, 98-102, 93-102) = max(5, 4, 9) = 9
        assert tr.iloc[1] == 9

    def test_missing_columns(self):
        """Test error when columns are missing."""
        df = pd.DataFrame({"high": [105], "low": [100]})

        with pytest.raises(PriceActionError):
            calculate_true_range(df)


class TestCalculateAvgDirectionalChange:
    """Tests for average directional change calculation."""

    def test_upward_trend(self):
        """Test upward directional change."""
        df = pd.DataFrame({"close": [100, 102, 104, 106, 108, 110]})
        avg_change, direction = calculate_avg_directional_change(df, period=5)

        assert direction == "up"
        assert avg_change > 0

    def test_downward_trend(self):
        """Test downward directional change."""
        df = pd.DataFrame({"close": [110, 108, 106, 104, 102, 100]})
        avg_change, direction = calculate_avg_directional_change(df, period=5)

        assert direction == "down"
        assert avg_change < 0

    def test_sideways_market(self):
        """Test sideways market."""
        df = pd.DataFrame({"close": [100, 101, 100, 101, 100, 100]})
        avg_change, direction = calculate_avg_directional_change(df, period=5)

        assert direction == "sideways"
        assert abs(avg_change) < 0.5

    def test_missing_column(self):
        """Test error when column is missing."""
        df = pd.DataFrame({"price": [100, 102]})

        with pytest.raises(PriceActionError):
            calculate_avg_directional_change(df)

    def test_insufficient_data(self):
        """Test error when insufficient data."""
        df = pd.DataFrame({"close": [100, 102]})

        with pytest.raises(InsufficientDataError):
            calculate_avg_directional_change(df, period=5)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame({"close": []})

        with pytest.raises(InsufficientDataError):
            detect_drop(df)

    def test_single_row(self):
        """Test with single row."""
        df = pd.DataFrame({"close": [100]})

        with pytest.raises(InsufficientDataError):
            detect_drop(df, lookback=1)

    def test_nan_values(self):
        """Test handling of NaN values."""
        df = pd.DataFrame({"close": [100, np.nan, 90]})
        drops = detect_drop(df, lookback=1)

        # Should handle NaN gracefully
        assert len(drops) == len(df)

    def test_zero_prices(self):
        """Test with zero prices (edge case)."""
        df = pd.DataFrame({"close": [0, 100]})
        drops = detect_drop(df, lookback=1)

        # Division by zero should result in inf
        assert drops.iloc[-1] == np.inf

    def test_negative_prices(self):
        """Test with negative prices (shouldn't happen)."""
        df = pd.DataFrame({"close": [100, -50]})
        drops = detect_drop(df, lookback=1)

        # Should calculate without error
        assert len(drops) == len(df)

    def test_very_large_prices(self):
        """Test with very large prices."""
        df = pd.DataFrame({"close": [1e9, 1.1e9]})
        drops = detect_drop(df, lookback=1)

        assert pytest.approx(drops.iloc[-1], rel=0.01) == 10.0

    def test_flat_prices(self):
        """Test with flat prices."""
        df = pd.DataFrame({"close": [100, 100, 100, 100]})
        drops = detect_drop(df, lookback=1)

        # All changes should be 0
        assert all(drops.iloc[1:] == 0.0)
