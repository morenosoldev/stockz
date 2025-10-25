"""Drop 5% Recovery Strategy.

Identifies stocks that:
- Drop 5-15% in a single day
- Show oversold RSI (< 30)
- Have volume spike (> 2x average)
- Are liquid (market cap > $1B, volume > 1M)

Recovery defined as: Price recovers 80% of drop within 5 days.
"""

from typing import Any

from src.strategies.base import BaseStrategy


class Drop5Strategy(BaseStrategy):
    """Drop 5% recovery detection strategy.

    This strategy identifies stocks that experience a significant single-day
    drop (5-15%) with oversold conditions and high volume, then predicts
    recovery probability based on technical indicators.

    The strategy uses a rules-based scoring system that considers:
    - Drop magnitude (ideal range: 5-15%)
    - RSI oversold condition (< 30)
    - Volume spike (> 2x average)
    - Distance from moving averages
    """

    name = "drop5"
    version = "1.0.0"

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """Pre-filter for liquid stocks with sufficient drop.

        Args:
            ticker_data: Basic ticker metadata

        Returns:
            True if ticker should be processed
        """
        # Require minimum liquidity
        if ticker_data.get("market_cap", 0) < 1_000_000_000:  # $1B minimum
            return False

        if ticker_data.get("avg_volume", 0) < 1_000_000:  # 1M shares minimum
            return False

        # Require drop in target range (5-15%)
        price_change_pct = ticker_data.get("price_change_pct", 0)
        if not (-15 <= price_change_pct <= -5):
            return False

        return True

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """Extract drop recovery features.

        Args:
            ticker_data: Detailed ticker data with bars and indicators

        Returns:
            Dictionary of computed features
        """
        bars = ticker_data.get("bars", [])
        indicators = ticker_data.get("indicators", {})

        if len(bars) < 2:
            return {
                "drop_pct": 0.0,
                "rsi": 50.0,
                "volume_ratio": 1.0,
                "sma_distance": 0.0,
                "atr": 0.0,
            }

        current = bars[-1]
        previous = bars[-2]

        # Calculate drop percentage
        drop_pct = ((current["close"] - previous["close"]) / previous["close"]) * 100

        # Volume ratio (current / 20-day average)
        volume_ratio = current["volume"] / indicators.get("volume_20d_avg", 1)

        # Distance from SMA20 (as percentage)
        sma_20 = indicators.get("sma_20", current["close"])
        sma_distance = ((current["close"] - sma_20) / sma_20) * 100

        return {
            "drop_pct": drop_pct,
            "rsi": indicators.get("rsi", 50.0),
            "volume_ratio": volume_ratio,
            "sma_distance": sma_distance,
            "atr": indicators.get("atr", 0.0),
        }

    def score(self, features: dict[str, Any]) -> float:
        """Compute recovery probability score.

        Scoring logic:
        - Base score: 0.5
        - Drop 5-15%: +0.15 (ideal range)
        - RSI < 30: +0.20 (oversold)
        - Volume > 2x avg: +0.15 (spike)
        - Below SMA20: +0.10 (mean reversion opportunity)

        Args:
            features: Feature dictionary

        Returns:
            Score between 0.0 and 1.0
        """
        score = 0.5  # Base score

        # Factor 1: Drop magnitude
        drop = abs(features.get("drop_pct", 0))
        if 5 <= drop <= 15:
            score += 0.15  # Ideal range
        elif drop > 15:
            score -= 0.10  # Too extreme, higher risk

        # Factor 2: RSI oversold
        rsi = features.get("rsi", 50)
        if rsi < 30:
            score += 0.20  # Strong oversold
        elif rsi < 40:
            score += 0.10  # Mild oversold
        elif rsi > 70:
            score -= 0.15  # Overbought (unlikely recovery)

        # Factor 3: Volume spike
        volume_ratio = features.get("volume_ratio", 1.0)
        if volume_ratio > 2.0:
            score += 0.15  # Strong interest
        elif volume_ratio > 1.5:
            score += 0.08  # Moderate interest

        # Factor 4: Distance from SMA
        sma_distance = features.get("sma_distance", 0)
        if sma_distance < -5:
            score += 0.10  # Below moving average (mean reversion)

        return self.validate_score(score)

    def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
        """Label whether recovery occurred.

        Recovery definition: Price recovers 80% of the drop within 5 days.

        Args:
            entry_data: Data at candidate identification
            outcome_data: Data after recovery window

        Returns:
            True if recovery occurred
        """
        entry_price = entry_data.get("entry_price", 0)
        drop_pct = abs(entry_data.get("features", {}).get("drop_pct", 0))
        max_price = outcome_data.get("max_price", 0)

        if entry_price == 0 or drop_pct == 0:
            return False

        # Calculate recovery percentage
        recovery_pct = ((max_price - entry_price) / entry_price) * 100

        # Recovery threshold: 80% of drop
        target_recovery = drop_pct * 0.8

        return bool(recovery_pct >= target_recovery)
