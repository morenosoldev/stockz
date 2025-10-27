"""Tests for Drop5 recovery strategy."""

import pytest

from src.strategies.drop5.implementation import Drop5Strategy


class TestDrop5Filters:
    """Test Drop5Strategy.filters() method."""

    def test_filter_pass_all_criteria(self):
        """Test that ticker passes all filter criteria."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,  # $5B
            "avg_volume": 2_000_000,  # 2M shares
            "price_change_pct": -7.5,  # -7.5% drop
        }

        assert strategy.filters(ticker_data)

    def test_filter_fail_market_cap_too_small(self):
        """Test that ticker fails with market cap < $1B."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 500_000_000,  # $500M (too small)
            "avg_volume": 2_000_000,
            "price_change_pct": -7.5,
        }

        assert not strategy.filters(ticker_data)

    def test_filter_fail_volume_too_low(self):
        """Test that ticker fails with volume < 1M."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 500_000,  # 500K (too low)
            "price_change_pct": -7.5,
        }

        assert not strategy.filters(ticker_data)

    def test_filter_fail_drop_too_small(self):
        """Test that ticker fails with drop < 5%."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 2_000_000,
            "price_change_pct": -3.0,  # Only -3% (too small)
        }

        assert not strategy.filters(ticker_data)

    def test_filter_fail_drop_too_large(self):
        """Test that ticker fails with drop > 15%."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 2_000_000,
            "price_change_pct": -20.0,  # -20% (too large)
        }

        assert not strategy.filters(ticker_data)

    def test_filter_fail_positive_change(self):
        """Test that ticker fails with positive price change."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 2_000_000,
            "price_change_pct": 5.0,  # Positive (not a drop)
        }

        assert not strategy.filters(ticker_data)

    def test_filter_edge_case_exactly_5_percent(self):
        """Test edge case: exactly 5% drop."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 2_000_000,
            "price_change_pct": -5.0,  # Exactly -5%
        }

        assert strategy.filters(ticker_data)

    def test_filter_edge_case_exactly_15_percent(self):
        """Test edge case: exactly 15% drop."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 2_000_000,
            "price_change_pct": -15.0,  # Exactly -15%
        }

        assert strategy.filters(ticker_data)

    def test_filter_edge_case_exactly_1b_market_cap(self):
        """Test edge case: exactly $1B market cap."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 1_000_000_000,  # Exactly $1B
            "avg_volume": 2_000_000,
            "price_change_pct": -7.5,
        }

        assert strategy.filters(ticker_data)

    def test_filter_edge_case_exactly_1m_volume(self):
        """Test edge case: exactly 1M volume."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            "avg_volume": 1_000_000,  # Exactly 1M
            "price_change_pct": -7.5,
        }

        assert strategy.filters(ticker_data)

    def test_filter_missing_fields(self):
        """Test behavior with missing fields (should fail)."""
        strategy = Drop5Strategy()

        ticker_data = {}  # No fields

        assert not strategy.filters(ticker_data)

    def test_filter_partial_data(self):
        """Test behavior with partial data."""
        strategy = Drop5Strategy()

        ticker_data = {
            "market_cap": 5_000_000_000,
            # Missing avg_volume and price_change_pct
        }

        assert not strategy.filters(ticker_data)


class TestDrop5Features:
    """Test Drop5Strategy.features() method."""

    def test_features_extraction(self):
        """Test feature extraction with complete data."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [
                {"close": 100.0, "volume": 1_000_000},  # Previous day
                {"close": 92.0, "volume": 3_000_000},  # Current day (-8%)
            ],
            "indicators": {
                "rsi": 25.0,
                "volume_20d_avg": 1_500_000,
                "sma_20": 105.0,
                "atr": 2.5,
            },
        }

        features = strategy.features(ticker_data)

        assert features["drop_pct"] == pytest.approx(-8.0, abs=0.01)
        assert features["rsi"] == 25.0
        assert features["volume_ratio"] == pytest.approx(2.0, abs=0.01)
        assert features["sma_distance"] == pytest.approx(-12.38, abs=0.01)
        assert features["atr"] == 2.5

    def test_features_insufficient_data(self):
        """Test feature extraction with insufficient bars."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [{"close": 100.0, "volume": 1_000_000}],  # Only 1 bar
            "indicators": {},
        }

        features = strategy.features(ticker_data)

        # Should return defaults
        assert features["drop_pct"] == 0.0
        assert features["rsi"] == 50.0
        assert features["volume_ratio"] == 1.0
        assert features["sma_distance"] == 0.0
        assert features["atr"] == 0.0

    def test_features_empty_bars(self):
        """Test feature extraction with no bars."""
        strategy = Drop5Strategy()

        ticker_data = {"bars": [], "indicators": {}}

        features = strategy.features(ticker_data)

        # Should return defaults
        assert features["drop_pct"] == 0.0
        assert features["rsi"] == 50.0
        assert features["volume_ratio"] == 1.0
        assert features["sma_distance"] == 0.0
        assert features["atr"] == 0.0

    def test_features_missing_indicators(self):
        """Test feature extraction with missing indicators."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [
                {"close": 100.0, "volume": 1_000_000},
                {"close": 92.0, "volume": 3_000_000},
            ],
            "indicators": {},  # Empty indicators
        }

        features = strategy.features(ticker_data)

        assert features["drop_pct"] == pytest.approx(-8.0, abs=0.01)
        assert features["rsi"] == 50.0  # Default
        assert features["volume_ratio"] == 3_000_000.0  # volume / 1 (default avg)
        assert features["sma_distance"] == 0.0  # SMA defaults to close
        assert features["atr"] == 0.0  # Default

    def test_features_price_increase(self):
        """Test feature extraction with price increase."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [
                {"close": 100.0, "volume": 1_000_000},
                {"close": 105.0, "volume": 1_200_000},  # +5%
            ],
            "indicators": {
                "rsi": 70.0,
                "volume_20d_avg": 1_000_000,
                "sma_20": 100.0,
                "atr": 2.0,
            },
        }

        features = strategy.features(ticker_data)

        assert features["drop_pct"] == pytest.approx(5.0, abs=0.01)
        assert features["rsi"] == 70.0
        assert features["volume_ratio"] == pytest.approx(1.2, abs=0.01)
        assert features["sma_distance"] == pytest.approx(5.0, abs=0.01)

    def test_features_above_sma(self):
        """Test SMA distance calculation when price is above SMA."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [
                {"close": 100.0, "volume": 1_000_000},
                {"close": 110.0, "volume": 1_200_000},
            ],
            "indicators": {"sma_20": 100.0, "volume_20d_avg": 1_000_000},
        }

        features = strategy.features(ticker_data)

        assert features["sma_distance"] == pytest.approx(10.0, abs=0.01)

    def test_features_below_sma(self):
        """Test SMA distance calculation when price is below SMA."""
        strategy = Drop5Strategy()

        ticker_data = {
            "bars": [
                {"close": 100.0, "volume": 1_000_000},
                {"close": 90.0, "volume": 1_200_000},
            ],
            "indicators": {"sma_20": 100.0, "volume_20d_avg": 1_000_000},
        }

        features = strategy.features(ticker_data)

        assert features["sma_distance"] == pytest.approx(-10.0, abs=0.01)


class TestDrop5Score:
    """Test Drop5Strategy.score() method."""

    def test_score_ideal_conditions(self):
        """Test scoring with ideal recovery conditions."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -7.5,  # Ideal range (5-15%)
            "rsi": 25.0,  # Strong oversold
            "volume_ratio": 2.5,  # Strong volume spike
            "sma_distance": -6.0,  # Below SMA (mean reversion)
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 + RSI: 0.20 + volume: 0.15 + SMA: 0.10 = 1.10 -> 1.0 (clamped)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_score_base_case(self):
        """Test scoring with neutral conditions."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -3.0,  # Below ideal range
            "rsi": 50.0,  # Neutral
            "volume_ratio": 1.0,  # No spike
            "sma_distance": 0.0,  # At SMA
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5, no bonuses
        assert score == pytest.approx(0.5, abs=0.01)

    def test_score_poor_conditions(self):
        """Test scoring with poor recovery conditions."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -20.0,  # Too extreme
            "rsi": 75.0,  # Overbought
            "volume_ratio": 0.8,  # Low volume
            "sma_distance": 5.0,  # Above SMA
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 - extreme drop: 0.10 - overbought: 0.15 = 0.25
        assert score == pytest.approx(0.25, abs=0.01)

    def test_score_mild_oversold(self):
        """Test scoring with mild oversold condition."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -7.5,
            "rsi": 35.0,  # Mild oversold
            "volume_ratio": 1.6,  # Moderate volume
            "sma_distance": -3.0,  # Slightly below SMA
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 + RSI: 0.10 + volume: 0.08 = 0.83
        assert score == pytest.approx(0.83, abs=0.01)

    def test_score_edge_5_percent(self):
        """Test scoring with exactly 5% drop."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -5.0,  # Exactly 5%
            "rsi": 50.0,
            "volume_ratio": 1.0,
            "sma_distance": 0.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 = 0.65
        assert score == pytest.approx(0.65, abs=0.01)

    def test_score_edge_15_percent(self):
        """Test scoring with exactly 15% drop."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -15.0,  # Exactly 15%
            "rsi": 50.0,
            "volume_ratio": 1.0,
            "sma_distance": 0.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 = 0.65
        assert score == pytest.approx(0.65, abs=0.01)

    def test_score_edge_30_rsi(self):
        """Test scoring with RSI exactly 30."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -7.5,
            "rsi": 30.0,  # Edge case (triggers < 40 but not < 30)
            "volume_ratio": 1.0,
            "sma_distance": 0.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 + RSI < 40: 0.10 = 0.75
        assert score == pytest.approx(0.75, abs=0.01)

    def test_score_edge_2x_volume(self):
        """Test scoring with exactly 2x volume."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -7.5,
            "rsi": 50.0,
            "volume_ratio": 2.0,  # Exactly 2x (triggers > 1.5 but not > 2.0)
            "sma_distance": 0.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Base: 0.5 + drop: 0.15 + volume > 1.5: 0.08 = 0.73
        assert score == pytest.approx(0.73, abs=0.01)

    def test_score_clamped_to_zero(self):
        """Test that score is clamped to 0.0 minimum."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -25.0,  # Very extreme
            "rsi": 80.0,  # Very overbought
            "volume_ratio": 0.5,
            "sma_distance": 10.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Score should be >= 0.0
        assert score >= 0.0

    def test_score_clamped_to_one(self):
        """Test that score is clamped to 1.0 maximum."""
        strategy = Drop5Strategy()

        features = {
            "drop_pct": -7.5,
            "rsi": 25.0,
            "volume_ratio": 3.0,
            "sma_distance": -10.0,
            "atr": 2.0,
        }

        score = strategy.score(features)

        # Score should be <= 1.0
        assert score <= 1.0

    def test_score_missing_features(self):
        """Test scoring with missing features (uses defaults)."""
        strategy = Drop5Strategy()

        features = {}  # Empty features

        score = strategy.score(features)

        # Base score: 0.5 (no features to apply)
        assert score == pytest.approx(0.5, abs=0.01)


class TestDrop5Label:
    """Test Drop5Strategy.label() method."""

    def test_label_recovery_occurred(self):
        """Test labeling when recovery occurred."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -10.0},  # -10% drop
        }

        outcome_data = {
            "max_price": 108.5,  # Recovered 8.5% (> 80% of 10% = 8%)
        }

        assert strategy.label(entry_data, outcome_data)

    def test_label_no_recovery(self):
        """Test labeling when no recovery occurred."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -10.0},
        }

        outcome_data = {
            "max_price": 105.0,  # Only recovered 5% (< 80% of 10% = 8%)
        }

        assert not strategy.label(entry_data, outcome_data)

    def test_label_exact_80_percent_recovery(self):
        """Test labeling with exactly 80% recovery."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -10.0},
        }

        outcome_data = {
            "max_price": 108.0,  # Exactly 8% recovery (80% of 10%)
        }

        assert strategy.label(entry_data, outcome_data)

    def test_label_full_recovery(self):
        """Test labeling with full recovery (100%+)."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -10.0},
        }

        outcome_data = {
            "max_price": 112.0,  # Recovered 12% (more than original drop)
        }

        assert strategy.label(entry_data, outcome_data)

    def test_label_small_drop(self):
        """Test labeling with small drop (easier to recover)."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -5.0},  # Small drop
        }

        outcome_data = {
            "max_price": 104.0,  # Recovered 4% (80% of 5% = 4%)
        }

        assert strategy.label(entry_data, outcome_data)

    def test_label_large_drop(self):
        """Test labeling with large drop (harder to recover)."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -15.0},  # Large drop
        }

        outcome_data = {
            "max_price": 112.0,  # Recovered 12% (80% of 15% = 12%)
        }

        assert strategy.label(entry_data, outcome_data)

    def test_label_missing_entry_price(self):
        """Test labeling with missing entry price."""
        strategy = Drop5Strategy()

        entry_data = {"features": {"drop_pct": -10.0}}

        outcome_data = {"max_price": 108.0}

        assert not strategy.label(entry_data, outcome_data)

    def test_label_missing_drop_pct(self):
        """Test labeling with missing drop percentage."""
        strategy = Drop5Strategy()

        entry_data = {"entry_price": 100.0, "features": {}}

        outcome_data = {"max_price": 108.0}

        assert not strategy.label(entry_data, outcome_data)

    def test_label_missing_max_price(self):
        """Test labeling with missing max price."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": -10.0},
        }

        outcome_data = {}

        assert not strategy.label(entry_data, outcome_data)

    def test_label_zero_entry_price(self):
        """Test labeling with zero entry price."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 0.0,
            "features": {"drop_pct": -10.0},
        }

        outcome_data = {"max_price": 108.0}

        assert not strategy.label(entry_data, outcome_data)

    def test_label_zero_drop_pct(self):
        """Test labeling with zero drop percentage."""
        strategy = Drop5Strategy()

        entry_data = {
            "entry_price": 100.0,
            "features": {"drop_pct": 0.0},
        }

        outcome_data = {"max_price": 108.0}

        assert not strategy.label(entry_data, outcome_data)


class TestDrop5StrategyProperties:
    """Test Drop5Strategy properties and metadata."""

    def test_strategy_name(self):
        """Test strategy name property."""
        strategy = Drop5Strategy()
        assert strategy.name == "drop5"

    def test_strategy_version(self):
        """Test strategy version property."""
        strategy = Drop5Strategy()
        assert strategy.version == "1.0.0"

    def test_strategy_config_schema(self):
        """Test strategy has config_schema."""
        strategy = Drop5Strategy()
        assert hasattr(strategy, "config_schema")

    def test_strategy_logger(self):
        """Test strategy has logger from BaseStrategy."""
        strategy = Drop5Strategy()
        assert hasattr(strategy, "logger")
        assert strategy.logger is not None
