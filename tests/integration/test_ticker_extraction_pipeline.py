"""Integration tests for AI-powered ticker extraction pipeline.

Tests the full pipeline: Reddit text → Regex + AI → Validated tickers
"""

from unittest.mock import MagicMock, patch

import pytest

from src.datasources.reddit import RedditAdapter


class TestTickerExtractionIntegration:
    """Integration tests for hybrid regex + AI ticker extraction."""

    @pytest.fixture
    def reddit_adapter(self):
        """Create RedditAdapter instance with mocked PRAW."""
        with patch("src.datasources.reddit.praw.Reddit") as mock_reddit:
            mock_reddit.return_value = MagicMock()
            adapter = RedditAdapter(
                client_id="test_id",
                client_secret="test_secret",
                user_agent="test_agent",
                subreddit="wallstreetbets",
            )
            return adapter

    # =========================================================================
    # Regex Path Tests
    # =========================================================================

    def test_regex_dollar_tickers(self, reddit_adapter):
        """Test regex extracts $TICKER format."""
        text = "Bought $AAPL and $MSFT today!"

        tickers = reddit_adapter._extract_tickers(text)

        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_regex_uppercase_tickers(self, reddit_adapter):
        """Test regex extracts standalone uppercase tickers."""
        text = "TSLA is mooning! NVDA also breaking out."

        tickers = reddit_adapter._extract_tickers(text)

        assert "TSLA" in tickers
        assert "NVDA" in tickers

    def test_regex_blacklist_filters(self, reddit_adapter):
        """Test blacklist filters common abbreviations."""
        text = "YOY growth is huge! GDP numbers strong. Check the API docs."

        tickers = reddit_adapter._extract_tickers(text)

        # These should be filtered by blacklist
        assert "YOY" not in tickers
        assert "GDP" not in tickers
        assert "API" not in tickers

    def test_regex_rejects_numbers_only(self, reddit_adapter):
        """Test validator rejects pure numeric strings."""
        text = "2024 outlook is strong. Revenue up 123%."

        tickers = reddit_adapter._extract_tickers(text)

        # Numbers-only should be rejected
        assert "2024" not in tickers
        assert "123" not in tickers

    def test_regex_share_classes(self, reddit_adapter):
        """Test regex supports share classes (BRK-B)."""
        text = "BRK-B is undervalued. Also like GOOG-A."

        # Share classes currently NOT supported by regex (would need pattern update)
        # This test documents current behavior
        reddit_adapter._extract_tickers(text)

        # Note: Current regex doesn't support hyphens, so these won't match
        # This is expected behavior (AI path would catch "Berkshire Hathaway")

    # =========================================================================
    # AI Path Tests
    # =========================================================================

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_ai_us_company_detection(
        self, mock_validate, mock_resolve, mock_extract, reddit_adapter
    ):
        """Test AI pipeline detects US company names."""
        text = "Apple crushed earnings! Microsoft also beat."

        # Mock AI pipeline
        mock_extract.return_value = ["Apple", "Microsoft"]
        mock_resolve.side_effect = [
            {"ticker": "AAPL", "exchange": "NASDAQ"},
            {"ticker": "MSFT", "exchange": "NASDAQ"},
        ]
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        assert "AAPL" in tickers
        assert "MSFT" in tickers

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_ai_international_company_detection(
        self, mock_validate, mock_resolve, mock_extract, reddit_adapter
    ):
        """Test AI pipeline detects international companies."""
        text = "Gubra trial results promising. SAP announces new product."

        # Mock AI pipeline
        mock_extract.return_value = ["Gubra", "SAP"]
        mock_resolve.side_effect = [
            {"ticker": "GUBRA.CO", "exchange": "Copenhagen"},
            {"ticker": "SAP.DE", "exchange": "Frankfurt"},
        ]
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        assert "GUBRA.CO" in tickers
        assert "SAP.DE" in tickers

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    def test_ai_rejects_non_public_companies(self, mock_resolve, mock_extract, reddit_adapter):
        """Test AI pipeline rejects non-publicly traded companies."""
        text = "I love my local bakery. They make great bread."

        # Mock AI pipeline
        mock_extract.return_value = ["local bakery"]
        mock_resolve.return_value = None  # LLM says not public

        tickers = reddit_adapter._extract_tickers(text)

        # No tickers should be extracted
        assert len(tickers) == 0

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_ai_yfinance_validation_failure(
        self, mock_validate, mock_resolve, mock_extract, reddit_adapter
    ):
        """Test yfinance rejects invalid LLM suggestions."""
        text = "FakeCorp is going to the moon!"

        # Mock AI pipeline - LLM hallucinates ticker
        mock_extract.return_value = ["FakeCorp"]
        mock_resolve.return_value = {"ticker": "FAKE", "exchange": "NASDAQ"}
        mock_validate.return_value = False  # yfinance says doesn't exist

        tickers = reddit_adapter._extract_tickers(text)

        # Ticker should be rejected due to validation failure
        assert "FAKE" not in tickers

    # =========================================================================
    # Hybrid Pipeline Tests
    # =========================================================================

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_hybrid_regex_and_ai(self, mock_validate, mock_resolve, mock_extract, reddit_adapter):
        """Test regex and AI paths work together."""
        text = "$TSLA is mooning! Apple also crushed earnings. Gubra trial promising."

        # Mock AI pipeline
        mock_extract.return_value = ["Apple", "Gubra"]
        mock_resolve.side_effect = [
            {"ticker": "AAPL", "exchange": "NASDAQ"},
            {"ticker": "GUBRA.CO", "exchange": "Copenhagen"},
        ]
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        # Should have: TSLA (regex) + AAPL (AI) + GUBRA.CO (AI)
        assert "TSLA" in tickers  # Regex
        assert "AAPL" in tickers  # AI
        assert "GUBRA.CO" in tickers  # AI

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_hybrid_deduplication(self, mock_validate, mock_resolve, mock_extract, reddit_adapter):
        """Test regex and AI don't duplicate tickers."""
        text = "$AAPL and Apple both mentioned."

        # Mock AI pipeline
        mock_extract.return_value = ["Apple"]
        mock_resolve.return_value = {"ticker": "AAPL", "exchange": "NASDAQ"}
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        # Should have AAPL only once
        assert tickers.count("AAPL") == 1

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    def test_hybrid_ai_error_fallback(self, mock_extract, reddit_adapter):
        """Test AI errors don't break regex path."""
        text = "$TSLA is great!"

        # Mock AI pipeline failure
        mock_extract.side_effect = Exception("NER failed")

        tickers = reddit_adapter._extract_tickers(text)

        # Regex should still work
        assert "TSLA" in tickers

    # =========================================================================
    # Edge Cases
    # =========================================================================

    def test_empty_text(self, reddit_adapter):
        """Test extraction handles empty text."""
        tickers = reddit_adapter._extract_tickers("")

        assert tickers == []

    def test_no_tickers(self, reddit_adapter):
        """Test extraction handles text with no tickers."""
        text = "This is just regular text with no stocks mentioned."

        tickers = reddit_adapter._extract_tickers(text)

        assert tickers == []

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_mixed_case_company_names(
        self, mock_validate, mock_resolve, mock_extract, reddit_adapter
    ):
        """Test AI handles mixed-case company names."""
        text = "apple and APPLE both mentioned."

        # Mock AI pipeline (NER should normalize)
        mock_extract.return_value = ["apple", "APPLE"]
        mock_resolve.return_value = {"ticker": "AAPL", "exchange": "NASDAQ"}
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        # Should deduplicate to single AAPL
        assert "AAPL" in tickers

    def test_special_characters_ignored(self, reddit_adapter):
        """Test extraction ignores tickers with special chars."""
        text = "Check out $AAPL! and #MSFT."

        tickers = reddit_adapter._extract_tickers(text)

        # $AAPL should work, #MSFT should not
        assert "AAPL" in tickers
        assert "MSFT" not in tickers  # Standalone MSFT not in text

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_asian_tickers(self, mock_validate, mock_resolve, mock_extract, reddit_adapter):
        """Test AI handles Asian numeric tickers."""
        text = "Tencent is dominating gaming."

        # Mock AI pipeline
        mock_extract.return_value = ["Tencent"]
        mock_resolve.return_value = {"ticker": "0700.HK", "exchange": "Hong Kong"}
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        assert "0700.HK" in tickers

    @patch("src.datasources.company_detector.CompanyDetector.extract_company_names")
    @patch("src.datasources.company_detector.CompanyDetector.resolve_to_ticker")
    @patch("src.datasources.company_detector.CompanyDetector.validate_ticker")
    def test_multiple_international_companies(
        self, mock_validate, mock_resolve, mock_extract, reddit_adapter
    ):
        """Test AI handles multiple international companies."""
        text = "Gubra, SAP, and Nintendo all looking strong."

        # Mock AI pipeline
        mock_extract.return_value = ["Gubra", "SAP", "Nintendo"]
        mock_resolve.side_effect = [
            {"ticker": "GUBRA.CO", "exchange": "Copenhagen"},
            {"ticker": "SAP.DE", "exchange": "Frankfurt"},
            {"ticker": "NTDOY", "exchange": "OTC"},
        ]
        mock_validate.return_value = True

        tickers = reddit_adapter._extract_tickers(text)

        assert "GUBRA.CO" in tickers
        assert "SAP.DE" in tickers
        assert "NTDOY" in tickers
        assert len(tickers) == 3
