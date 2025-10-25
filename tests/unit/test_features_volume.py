"""
Tests for volume analysis functions.

Tests cover:
- RVOL calculations
- Volume spike detection
- Volume trends
- Price-volume confirmation
- Accumulation/Distribution
- On-Balance Volume
- Volume profiles
"""

import pandas as pd
import pytest

from src.features.volume import (
    InsufficientDataError,
    VolumeAnalysisError,
    calculate_rvol,
    calculate_volume_profile,
    calculate_volume_trend,
    confirm_price_move_with_volume,
    detect_accumulation_distribution,
    detect_on_balance_volume,
    detect_volume_spike,
    is_volume_confirmed_drop,
)


class TestCalculateRVOL:
    """Tests for RVOL calculation."""

    def test_basic_rvol(self):
        """Test basic RVOL calculation."""
        df = pd.DataFrame({"volume": [1000, 1000, 1000, 2000]})
        rvol = calculate_rvol(df, period=3)

        # Last RVOL should be > 1.0 (2000 is higher than average)
        # Uses EMA so not exactly 2.0
        assert rvol.iloc[-1] > 1.0

    def test_rvol_below_average(self):
        """Test RVOL below average."""
        df = pd.DataFrame({"volume": [2000, 2000, 2000, 1000]})
        rvol = calculate_rvol(df, period=3)

        # Last RVOL should be < 1.0 (1000 is lower than average)
        assert rvol.iloc[-1] < 1.0

    def test_rvol_insufficient_data(self):
        """Test RVOL with insufficient data."""
        df = pd.DataFrame({"volume": [1000, 2000]})

        with pytest.raises(InsufficientDataError):
            calculate_rvol(df, period=5)

    def test_rvol_missing_column(self):
        """Test RVOL with missing column."""
        df = pd.DataFrame({"price": [100, 101]})

        with pytest.raises(VolumeAnalysisError):
            calculate_rvol(df, period=2)

    def test_rvol_custom_column(self):
        """Test RVOL with custom column name."""
        df = pd.DataFrame({"vol": [1000, 1000, 2000]})
        rvol = calculate_rvol(df, period=2, volume_col="vol")

        # Should be > 1.0 since last volume is higher
        assert rvol.iloc[-1] > 1.0

    def test_rvol_handles_zero_volume(self):
        """Test RVOL handles zero volume gracefully."""
        df = pd.DataFrame({"volume": [0, 0, 1000]})
        rvol = calculate_rvol(df, period=2)

        # Should not raise, should handle division by zero
        assert not rvol.isna().any()


class TestDetectVolumeSpike:
    """Tests for volume spike detection."""

    def test_detect_spike(self):
        """Test detection of volume spike."""
        df = pd.DataFrame({"volume": [1000, 1000, 1000, 5000]})
        spikes = detect_volume_spike(df, threshold=2.0, period=3)

        assert spikes.iloc[-1]

    def test_no_spike(self):
        """Test no volume spike."""
        # Need enough data for default period (20)
        volumes = [1000] * 20 + [1100]
        df = pd.DataFrame({"volume": volumes})
        spikes = detect_volume_spike(df, threshold=2.0)

        assert not spikes.iloc[-1]

    def test_spike_threshold(self):
        """Test different spike thresholds."""
        df = pd.DataFrame({"volume": [1000, 1000, 1000, 2500]})

        # RVOL = 2500 / avg(1000,1000,2500) = 2500/1500 = 1.67
        # Should NOT spike with threshold 2.0 (1.67 < 2.0)
        spikes_low = detect_volume_spike(df, threshold=1.5, period=3)
        assert spikes_low.iloc[-1]

        # Should not spike with threshold 2.0 (1.67 < 2.0)
        spikes_high = detect_volume_spike(df, threshold=2.0, period=3)
        assert not spikes_high.iloc[-1]


class TestCalculateVolumeTrend:
    """Tests for volume trend calculation."""

    def test_increasing_trend(self):
        """Test increasing volume trend."""
        # Gradually increasing volume
        df = pd.DataFrame({"volume": list(range(1000, 1050))})
        trend = calculate_volume_trend(df, short_period=5, long_period=10)

        # Short MA should be higher than long MA
        assert trend.iloc[-1] > 0

    def test_decreasing_trend(self):
        """Test decreasing volume trend."""
        # Gradually decreasing volume
        df = pd.DataFrame({"volume": list(range(1050, 1000, -1))})
        trend = calculate_volume_trend(df, short_period=5, long_period=10)

        # Short MA should be lower than long MA
        assert trend.iloc[-1] < 0

    def test_flat_trend(self):
        """Test flat volume trend."""
        df = pd.DataFrame({"volume": [1000] * 50})
        trend = calculate_volume_trend(df, short_period=5, long_period=10)

        # Should be approximately 0
        assert abs(trend.iloc[-1]) < 0.01

    def test_trend_insufficient_data(self):
        """Test trend with insufficient data."""
        df = pd.DataFrame({"volume": [1000, 1100, 1200]})

        with pytest.raises(InsufficientDataError):
            calculate_volume_trend(df, short_period=5, long_period=10)


class TestConfirmPriceMoveWithVolume:
    """Tests for price move confirmation."""

    def test_confirmed_move(self):
        """Test price move confirmed by volume."""
        confirmed = confirm_price_move_with_volume(5.0, 2.0, min_rvol=1.5)
        assert confirmed is True

    def test_unconfirmed_move(self):
        """Test price move not confirmed by volume."""
        confirmed = confirm_price_move_with_volume(-5.0, 1.2, min_rvol=1.5)
        assert confirmed is False

    def test_series_confirmation(self):
        """Test confirmation with Series."""
        price_changes = pd.Series([5.0, -3.0, 2.0])
        rvols = pd.Series([2.0, 1.2, 1.8])

        confirmed = confirm_price_move_with_volume(price_changes, rvols, min_rvol=1.5)

        assert confirmed.iloc[0]
        assert not confirmed.iloc[1]
        assert confirmed.iloc[2]


class TestDetectAccumulationDistribution:
    """Tests for A/D Line calculation."""

    def test_accumulation(self):
        """Test accumulation (buying pressure)."""
        # Closes near high = accumulation
        df = pd.DataFrame(
            {
                "close": [100.8, 101.8, 102.8],  # Close near high
                "high": [101, 102, 103],
                "low": [100, 101, 102],
                "volume": [1000, 1000, 1000],
            }
        )
        ad = detect_accumulation_distribution(df)

        # A/D should be increasing (positive accumulation)
        assert ad.iloc[-1] > 0

    def test_distribution(self):
        """Test distribution (selling pressure)."""
        # Closes near low = distribution
        df = pd.DataFrame(
            {
                "close": [100.2, 99.2, 98.2],  # Close near low
                "high": [101, 100, 99],
                "low": [100, 99, 98],
                "volume": [1000, 1000, 1000],
            }
        )
        ad = detect_accumulation_distribution(df)

        # A/D should be negative (distribution)
        assert ad.iloc[-1] < 0

    def test_ad_missing_columns(self):
        """Test A/D with missing columns."""
        df = pd.DataFrame({"close": [100, 101]})

        with pytest.raises(VolumeAnalysisError):
            detect_accumulation_distribution(df)

    def test_ad_handles_zero_range(self):
        """Test A/D handles zero range (high == low)."""
        df = pd.DataFrame(
            {
                "close": [100, 100, 100],
                "high": [100, 100, 100],
                "low": [100, 100, 100],
                "volume": [1000, 1000, 1000],
            }
        )
        ad = detect_accumulation_distribution(df)

        # Should not raise, should handle gracefully
        assert not ad.isna().any()


class TestDetectOnBalanceVolume:
    """Tests for OBV calculation."""

    def test_obv_uptrend(self):
        """Test OBV in uptrend."""
        df = pd.DataFrame(
            {
                "close": [100, 102, 104, 106],
                "volume": [1000, 1200, 1100, 1300],
            }
        )
        obv = detect_on_balance_volume(df)

        # OBV should be positive and increasing
        assert obv.iloc[-1] > 0
        assert obv.iloc[-1] > obv.iloc[1]

    def test_obv_downtrend(self):
        """Test OBV in downtrend."""
        df = pd.DataFrame(
            {
                "close": [106, 104, 102, 100],
                "volume": [1000, 1200, 1100, 1300],
            }
        )
        obv = detect_on_balance_volume(df)

        # OBV should be negative and decreasing
        assert obv.iloc[-1] < 0
        assert obv.iloc[-1] < obv.iloc[1]

    def test_obv_flat(self):
        """Test OBV when price is flat."""
        df = pd.DataFrame(
            {
                "close": [100, 100, 100, 100],
                "volume": [1000, 1200, 1100, 1300],
            }
        )
        obv = detect_on_balance_volume(df)

        # OBV should remain at 0
        assert obv.iloc[-1] == 0

    def test_obv_missing_columns(self):
        """Test OBV with missing columns."""
        df = pd.DataFrame({"close": [100, 101]})

        with pytest.raises(VolumeAnalysisError):
            detect_on_balance_volume(df)


class TestIsVolumeConfirmedDrop:
    """Tests for volume-confirmed drop detection."""

    def test_confirmed_drop(self):
        """Test drop confirmed by high volume."""
        df = pd.DataFrame(
            {
                "close": [100, 100, 100, 95],
                "volume": [1000, 1000, 1000, 4000],  # RVOL = 4000/2000 = 2.0
            }
        )
        confirmed = is_volume_confirmed_drop(df, -5.0, min_rvol=2.0)
        assert confirmed

    def test_unconfirmed_drop(self):
        """Test drop not confirmed by volume."""
        df = pd.DataFrame(
            {
                "close": [100, 100, 100, 95],
                "volume": [1000, 1000, 1000, 1100],
            }
        )
        confirmed = is_volume_confirmed_drop(df, -5.0, min_rvol=2.0)
        assert not confirmed

    def test_insufficient_data(self):
        """Test with insufficient data."""
        df = pd.DataFrame(
            {
                "close": [100],
                "volume": [1000],
            }
        )
        confirmed = is_volume_confirmed_drop(df, -5.0)
        assert confirmed is False


class TestCalculateVolumeProfile:
    """Tests for volume profile calculation."""

    def test_basic_profile(self):
        """Test basic volume profile."""
        df = pd.DataFrame(
            {
                "close": [100, 102, 101, 103, 100],
                "volume": [1000, 1200, 1100, 1300, 900],
            }
        )
        profile = calculate_volume_profile(df, num_bins=5)

        assert "price_level" in profile.columns
        assert "volume" in profile.columns
        assert "pct_volume" in profile.columns
        assert len(profile) == 5

    def test_profile_percentages_sum_to_100(self):
        """Test that volume percentages sum to ~100%."""
        df = pd.DataFrame(
            {
                "close": [100, 102, 101, 103, 100],
                "volume": [1000, 1200, 1100, 1300, 900],
            }
        )
        profile = calculate_volume_profile(df, num_bins=5)

        assert pytest.approx(profile["pct_volume"].sum(), rel=0.01) == 100.0

    def test_profile_flat_price(self):
        """Test profile when all prices are the same."""
        df = pd.DataFrame(
            {
                "close": [100, 100, 100, 100],
                "volume": [1000, 1200, 1100, 1300],
            }
        )
        profile = calculate_volume_profile(df, num_bins=5)

        # Should return single bin with all volume
        assert len(profile) == 1
        assert profile["price_level"].iloc[0] == 100.0
        assert profile["pct_volume"].iloc[0] == 100.0

    def test_profile_missing_columns(self):
        """Test profile with missing columns."""
        df = pd.DataFrame({"close": [100, 101]})

        with pytest.raises(VolumeAnalysisError):
            calculate_volume_profile(df)

    def test_profile_sorted_by_price(self):
        """Test that profile is sorted by price level."""
        df = pd.DataFrame(
            {
                "close": [105, 100, 103, 101, 102],
                "volume": [1000, 1200, 1100, 1300, 900],
            }
        )
        profile = calculate_volume_profile(df, num_bins=5)

        # Price levels should be in ascending order
        price_levels = profile["price_level"].tolist()
        assert price_levels == sorted(price_levels)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pd.DataFrame({"volume": []})

        with pytest.raises(InsufficientDataError):
            calculate_rvol(df, period=5)

    def test_single_row(self):
        """Test with single row."""
        df = pd.DataFrame({"volume": [1000]})

        with pytest.raises(InsufficientDataError):
            calculate_rvol(df, period=2)

    def test_negative_volume(self):
        """Test handling of negative volume (shouldn't happen but check)."""
        df = pd.DataFrame({"volume": [1000, -500, 1200, 1100]})
        rvol = calculate_rvol(df, period=3)

        # Should calculate without error
        assert len(rvol) == len(df)

    def test_very_large_volume(self):
        """Test with very large volume values."""
        df = pd.DataFrame({"volume": [1e9, 1e9, 1e9, 2e9]})
        rvol = calculate_rvol(df, period=3)

        # Last RVOL = 2e9 / avg(1e9, 1e9, 2e9) = 2e9 / 1.333e9 = 1.5
        assert pytest.approx(rvol.iloc[-1], rel=0.01) == 1.5
