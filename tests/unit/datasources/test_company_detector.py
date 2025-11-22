"""Unit tests for CompanyDetector (AI-powered company name detection)."""

from unittest.mock import MagicMock, patch

import pytest

from src.datasources.company_detector import CompanyDetector


class TestCompanyDetector:
    """Test suite for CompanyDetector."""

    @pytest.fixture
    def detector(self):
        """Create CompanyDetector instance."""
        return CompanyDetector()

    # =========================================================================
    # Stage 1: Named Entity Recognition (NER)
    # =========================================================================

    def test_extract_company_names_us_companies(self, detector):
        """Test NER extracts US company names."""
        text = "Apple crushed earnings! Microsoft also beat estimates."

        with patch.object(detector, "nlp") as mock_nlp:
            # Mock spaCy entities
            mock_doc = MagicMock()
            mock_doc.ents = [
                MagicMock(text="Apple", label_="ORG"),
                MagicMock(text="Microsoft", label_="ORG"),
            ]
            mock_nlp.return_value = mock_doc

            companies = detector.extract_company_names(text)

            assert "Apple" in companies
            assert "Microsoft" in companies
            assert len(companies) == 2

    def test_extract_company_names_international(self, detector):
        """Test NER extracts international company names."""
        text = "Gubra trial results promising. SAP announces new product."

        with patch.object(detector, "nlp") as mock_nlp:
            mock_doc = MagicMock()
            mock_doc.ents = [
                MagicMock(text="Gubra", label_="ORG"),
                MagicMock(text="SAP", label_="ORG"),
            ]
            mock_nlp.return_value = mock_doc

            companies = detector.extract_company_names(text)

            assert "Gubra" in companies
            assert "SAP" in companies

    def test_extract_company_names_products(self, detector):
        """Test NER extracts product entities (potential companies)."""
        text = "I love my iPhone and Tesla."

        with patch.object(detector, "nlp") as mock_nlp:
            mock_doc = MagicMock()
            mock_doc.ents = [
                MagicMock(text="iPhone", label_="PRODUCT"),
                MagicMock(text="Tesla", label_="ORG"),
            ]
            mock_nlp.return_value = mock_doc

            companies = detector.extract_company_names(text)

            # Both ORG and PRODUCT labels should be extracted
            assert "iPhone" in companies or "Tesla" in companies

    def test_extract_company_names_no_entities(self, detector):
        """Test NER returns empty list when no entities detected."""
        text = "This is just regular text with no companies."

        with patch.object(detector, "nlp") as mock_nlp:
            mock_doc = MagicMock()
            mock_doc.ents = []
            mock_nlp.return_value = mock_doc

            companies = detector.extract_company_names(text)

            assert companies == []

    def test_extract_company_names_nlp_not_loaded(self, detector):
        """Test NER fails gracefully when spaCy model not loaded."""
        detector.nlp = None  # Simulate model not loaded

        companies = detector.extract_company_names("Apple is great")

        assert companies == []

    def test_extract_company_names_nlp_error(self, detector):
        """Test NER handles exceptions gracefully."""
        with patch.object(detector, "nlp") as mock_nlp:
            mock_nlp.side_effect = Exception("NER processing failed")

            companies = detector.extract_company_names("Apple is great")

            assert companies == []

    # =========================================================================
    # Stage 2: LLM Ticker Resolution
    # =========================================================================

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_us_company(self, mock_openai_class, detector):
        """Test LLM resolves US company to ticker."""
        # Mock OpenAI response
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"ticker": "AAPL", "exchange": "NASDAQ"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = detector.resolve_to_ticker("Apple")

        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["exchange"] == "NASDAQ"

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_international(self, mock_openai_class, detector):
        """Test LLM resolves international company with exchange suffix."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"ticker": "GUBRA.CO", "exchange": "Copenhagen"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = detector.resolve_to_ticker("Gubra")

        assert result is not None
        assert result["ticker"] == "GUBRA.CO"
        assert result["exchange"] == "Copenhagen"

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_not_public(self, mock_openai_class, detector):
        """Test LLM rejects non-publicly traded companies."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content='{"ticker": null}'))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = detector.resolve_to_ticker("My Local Bakery")

        assert result is None

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_invalid_json(self, mock_openai_class, detector):
        """Test LLM handles invalid JSON gracefully."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock(message=MagicMock(content="Invalid JSON response"))]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        result = detector.resolve_to_ticker("Apple")

        assert result is None

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_api_error(self, mock_openai_class, detector):
        """Test LLM handles API errors gracefully."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("OpenAI API error")
        mock_openai_class.return_value = mock_client

        result = detector.resolve_to_ticker("Apple")

        assert result is None

    @patch("openai.OpenAI")
    def test_resolve_to_ticker_caching(self, mock_openai_class, detector):
        """Test LLM resolution results are cached."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content='{"ticker": "AAPL", "exchange": "NASDAQ"}'))
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # First call - should hit API
        result1 = detector.resolve_to_ticker("Apple")
        assert mock_client.chat.completions.create.call_count == 1

        # Second call - should use cache
        result2 = detector.resolve_to_ticker("Apple")
        assert mock_client.chat.completions.create.call_count == 1  # No additional call

        assert result1 == result2

    # =========================================================================
    # Stage 3: yfinance Validation
    # =========================================================================

    @patch("yfinance.Ticker")
    def test_validate_ticker_exists(self, mock_ticker_class, detector):
        """Test yfinance validates existing ticker."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"symbol": "AAPL", "regularMarketPrice": 150.0}
        mock_ticker_class.return_value = mock_ticker

        result = detector.validate_ticker("AAPL")

        assert result is True

    @patch("yfinance.Ticker")
    def test_validate_ticker_not_exists(self, mock_ticker_class, detector):
        """Test yfinance rejects non-existent ticker."""
        mock_ticker = MagicMock()
        mock_ticker.info = {}  # Empty info = ticker doesn't exist
        mock_ticker_class.return_value = mock_ticker

        result = detector.validate_ticker("FAKESYMBOL123")

        assert result is False

    @patch("yfinance.Ticker")
    def test_validate_ticker_international(self, mock_ticker_class, detector):
        """Test yfinance validates international ticker with suffix."""
        mock_ticker = MagicMock()
        mock_ticker.info = {
            "symbol": "GUBRA.CO",
            "currentPrice": 245.50,
            "currency": "DKK",
        }
        mock_ticker_class.return_value = mock_ticker

        result = detector.validate_ticker("GUBRA.CO")

        assert result is True

    @patch("yfinance.Ticker")
    def test_validate_ticker_error(self, mock_ticker_class, detector):
        """Test yfinance handles API errors gracefully."""
        mock_ticker_class.side_effect = Exception("yfinance API error")

        result = detector.validate_ticker("AAPL")

        assert result is False

    @patch("yfinance.Ticker")
    def test_validate_ticker_caching(self, mock_ticker_class, detector):
        """Test yfinance validation results are cached."""
        mock_ticker = MagicMock()
        mock_ticker.info = {"symbol": "AAPL", "regularMarketPrice": 150.0}
        mock_ticker_class.return_value = mock_ticker

        # First call - should hit API
        result1 = detector.validate_ticker("AAPL")
        assert mock_ticker_class.call_count == 1

        # Second call - should use cache
        result2 = detector.validate_ticker("AAPL")
        assert mock_ticker_class.call_count == 1  # No additional call

        assert result1 == result2
        assert result1 is True
