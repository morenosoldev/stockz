"""Unit tests for balanced sentiment scoring (Task 6.3).

Tests the new three-dimensional scoring system:
- Fundamentals (30%)
- Potential (40%)
- Conviction (30%)
"""

from unittest.mock import Mock, patch

import pytest

from src.datasources.sentiment import SentimentAnalyzer, SentimentScore, calculate_weighted_score


class TestCalculateWeightedScore:
    """Test the weighted score calculation function."""

    def test_strong_fundamentals_weak_potential_bullish(self):
        """Strong fundamentals + weak potential = moderate bullish."""
        score = calculate_weighted_score(
            fundamentals=0.8, potential=0.3, conviction=0.7, sentiment="bullish"
        )
        # Expected: 0.8*0.3 + 0.3*0.4 + 0.7*0.3 = 0.24 + 0.12 + 0.21 = 0.57
        assert score == pytest.approx(0.57, abs=0.01)

    def test_weak_fundamentals_high_potential_bullish(self):
        """Weak fundamentals + high potential = strong bullish (user's key request)."""
        score = calculate_weighted_score(
            fundamentals=0.2, potential=0.9, conviction=0.7, sentiment="bullish"
        )
        # Expected: 0.2*0.3 + 0.9*0.4 + 0.7*0.3 = 0.06 + 0.36 + 0.21 = 0.63
        assert score == pytest.approx(0.63, abs=0.01)
        assert score > 0.5  # Should be bullish despite weak fundamentals

    def test_strong_all_dimensions_bullish(self):
        """Strong fundamentals + potential + conviction = very bullish."""
        score = calculate_weighted_score(
            fundamentals=0.8, potential=0.9, conviction=0.9, sentiment="bullish"
        )
        # Expected: 0.8*0.3 + 0.9*0.4 + 0.9*0.3 = 0.24 + 0.36 + 0.27 = 0.87
        assert score == pytest.approx(0.87, abs=0.01)

    def test_weak_all_dimensions_bearish(self):
        """Weak fundamentals + no potential = bearish."""
        score = calculate_weighted_score(
            fundamentals=0.2, potential=0.2, conviction=0.4, sentiment="bearish"
        )
        # Expected: -(0.2*0.3 + 0.2*0.4 + 0.4*0.3) = -(0.06 + 0.08 + 0.12) = -0.26
        assert score == pytest.approx(-0.26, abs=0.01)

    def test_neutral_sentiment(self):
        """Neutral sentiment always returns 0."""
        score = calculate_weighted_score(
            fundamentals=0.8, potential=0.8, conviction=0.8, sentiment="neutral"
        )
        assert score == 0.0

    def test_high_potential_dominates_weak_fundamentals(self):
        """Potential (40% weight) should dominate fundamentals (30% weight)."""
        # Weak fundamentals, high potential
        score_high_potential = calculate_weighted_score(0.2, 0.9, 0.6, "bullish")

        # High fundamentals, weak potential
        score_low_potential = calculate_weighted_score(0.9, 0.2, 0.6, "bullish")

        # High potential should score higher
        assert score_high_potential > score_low_potential


class TestSentimentAnalyzerBalanced:
    """Test the SentimentAnalyzer with balanced prompts."""

    @patch("src.datasources.sentiment.OpenAI")
    def test_sentiment_score_has_new_fields(self, mock_openai):
        """Ensure new fields (fundamentals_score, potential_score, etc.) are present."""
        # Mock LLM response
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.parsed = SentimentScore(
            ticker="NVDA",
            sentiment="bullish",
            confidence=0.85,
            score=0.75,
            fundamentals_score=0.7,
            potential_score=0.9,
            conviction_score=0.8,
            reasoning="Strong AI growth potential despite high valuation",
            catalysts=["AI chip demand", "New GPU launch"],
            risk_factors=["High valuation"],
            growth_drivers=["AI market expansion", "Data center demand"],
        )

        mock_openai_instance = Mock()
        mock_openai_instance.beta.chat.completions.parse.return_value = mock_completion
        mock_openai.return_value = mock_openai_instance

        analyzer = SentimentAnalyzer(cache_enabled=False)
        result = analyzer.analyze_post("NVDA", "NVDA crushing it with AI", "")

        # Check new fields exist
        assert hasattr(result, "fundamentals_score")
        assert hasattr(result, "potential_score")
        assert hasattr(result, "conviction_score")
        assert hasattr(result, "growth_drivers")

        # Check values
        assert result.fundamentals_score == 0.7
        assert result.potential_score == 0.9
        assert result.conviction_score == 0.8
        assert result.growth_drivers == ["AI market expansion", "Data center demand"]

    @patch("src.datasources.sentiment.OpenAI")
    def test_weak_fundamentals_high_potential_bullish(self, mock_openai):
        """Test case matching user's request: weak company with exciting potential."""
        # Mock LLM response for a pre-revenue biotech with breakthrough tech
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.parsed = SentimentScore(
            ticker="BIOT",
            sentiment="bullish",
            confidence=0.82,
            score=0.65,
            fundamentals_score=0.25,  # Weak - pre-revenue, burning cash
            potential_score=0.95,  # Very high - breakthrough cancer treatment
            conviction_score=0.75,  # Good - author cited specific trials, dates
            reasoning="Despite cash burn, breakthrough cancer treatment with Phase 2 trials Q1 2026 represents massive potential",
            catalysts=["Phase 2 trials Q1 2026", "Breakthrough cancer treatment", "$200B market"],
            risk_factors=["Cash burn", "Clinical trial risk", "Pre-revenue"],
            growth_drivers=["First-to-market AI drug discovery", "200B TAM", "Platform approach"],
        )

        mock_openai_instance = Mock()
        mock_openai_instance.beta.chat.completions.parse.return_value = mock_completion
        mock_openai.return_value = mock_openai_instance

        analyzer = SentimentAnalyzer(cache_enabled=False)
        result = analyzer.analyze_post(
            "BIOT",
            "BIOT breakthrough cancer treatment",
            "Phase 2 trials starting Q1 2026, could disrupt $200B market",
        )

        # Weak fundamentals
        assert result.fundamentals_score < 0.3

        # High potential
        assert result.potential_score > 0.9

        # Overall bullish despite weak fundamentals
        assert result.sentiment == "bullish"
        assert result.score > 0.5  # Still positive score

        # Calculate weighted score
        weighted = calculate_weighted_score(
            result.fundamentals_score,
            result.potential_score,
            result.conviction_score,
            result.sentiment,
        )
        # 0.25*0.3 + 0.95*0.4 + 0.75*0.3 = 0.075 + 0.38 + 0.225 = 0.68
        assert weighted == pytest.approx(0.68, abs=0.01)
        assert weighted > 0.6  # Strong positive score

    @patch("src.datasources.sentiment.OpenAI")
    def test_pure_hype_low_conviction(self, mock_openai):
        """Pure hype with no substance should have low conviction."""
        # Mock LLM response for "TO THE MOON 🚀🚀🚀" type comment
        mock_completion = Mock()
        mock_completion.choices = [Mock()]
        mock_completion.choices[0].message.parsed = SentimentScore(
            ticker="GME",
            sentiment="neutral",  # Should be neutral due to low conviction
            confidence=0.3,
            score=0.0,
            fundamentals_score=0.5,  # Unknown
            potential_score=0.3,  # Vague
            conviction_score=0.1,  # Pure speculation
            reasoning="Pure hype with no factual basis or specific catalysts",
            catalysts=[],
            risk_factors=["Pure speculation", "No research"],
            growth_drivers=[],
        )

        mock_openai_instance = Mock()
        mock_openai_instance.beta.chat.completions.parse.return_value = mock_completion
        mock_openai.return_value = mock_openai_instance

        analyzer = SentimentAnalyzer(cache_enabled=False)
        result = analyzer.analyze_post("GME", "GME TO THE MOON 🚀🚀🚀", "BUY NOW!!!")

        # Low conviction
        assert result.conviction_score < 0.3

        # Should be neutral or low confidence
        assert result.confidence < 0.5 or result.sentiment == "neutral"

    def test_potential_weighs_more_than_fundamentals(self):
        """Ensure potential (40%) weighs more than fundamentals (30%)."""
        # High potential, low fundamentals
        score_a = calculate_weighted_score(0.2, 0.9, 0.6, "bullish")

        # Low potential, high fundamentals
        score_b = calculate_weighted_score(0.9, 0.2, 0.6, "bullish")

        # Score A (high potential) should be higher
        assert score_a > score_b

        # Calculate the difference
        # Score A: 0.2*0.3 + 0.9*0.4 + 0.6*0.3 = 0.06 + 0.36 + 0.18 = 0.60
        # Score B: 0.9*0.3 + 0.2*0.4 + 0.6*0.3 = 0.27 + 0.08 + 0.18 = 0.53
        assert score_a == pytest.approx(0.60, abs=0.01)
        assert score_b == pytest.approx(0.53, abs=0.01)


class TestRealWorldScenarios:
    """Test real-world scenarios from the task specification."""

    def test_scenario_profitable_but_stagnant(self):
        """Profitable but stagnant company = moderate score."""
        score = calculate_weighted_score(
            fundamentals=0.8,  # Strong fundamentals
            potential=0.3,  # Weak growth prospects
            conviction=0.7,  # Well-researched
            sentiment="bullish",
        )
        # 0.8*0.3 + 0.3*0.4 + 0.7*0.3 = 0.24 + 0.12 + 0.21 = 0.57
        assert 0.4 < score < 0.7  # Neutral-positive range

    def test_scenario_unprofitable_breakthrough_tech(self):
        """Unprofitable but breakthrough tech = strong bullish."""
        score = calculate_weighted_score(
            fundamentals=0.2,  # Weak fundamentals (burning cash)
            potential=0.95,  # Very high potential
            conviction=0.75,  # Good research
            sentiment="bullish",
        )
        # 0.2*0.3 + 0.95*0.4 + 0.75*0.3 = 0.06 + 0.38 + 0.225 = 0.665
        assert score > 0.6  # Strong bullish despite weak fundamentals

    def test_scenario_profitable_plus_catalysts(self):
        """Profitable + exciting catalysts = very bullish."""
        score = calculate_weighted_score(
            fundamentals=0.85,  # Strong
            potential=0.9,  # High
            conviction=0.9,  # Deep research
            sentiment="bullish",
        )
        # 0.85*0.3 + 0.9*0.4 + 0.9*0.3 = 0.255 + 0.36 + 0.27 = 0.885
        assert score > 0.8  # Very bullish

    def test_scenario_weak_no_catalysts(self):
        """Weak fundamentals + no catalysts = bearish."""
        score = calculate_weighted_score(
            fundamentals=0.2,  # Weak
            potential=0.2,  # No growth
            conviction=0.4,  # Some research
            sentiment="bearish",
        )
        # -(0.2*0.3 + 0.2*0.4 + 0.4*0.3) = -(0.06 + 0.08 + 0.12) = -0.26
        assert score < -0.2  # Bearish
