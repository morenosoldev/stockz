"""Unit tests for company adapter."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pytest

from src.datasources.attribution import Attribution, DataSource
from src.datasources.company import CompanyAdapter, CompanyData


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before each test to avoid interference."""
    import shutil
    from pathlib import Path

    cache_path = Path("data/cache/company")
    if cache_path.exists():
        shutil.rmtree(cache_path)

    yield

    # Clean up after test
    if cache_path.exists():
        shutil.rmtree(cache_path)


@pytest.fixture
def mock_company_response():
    """Mock OpenAI response for company research."""
    return {
        "company_name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "description": "Apple designs, manufactures, and markets consumer electronics.",
        "headquarters": "Cupertino, CA",
        "employees": 164000,
        "founded_year": 1976,
        "market_cap": 2800000,
        "revenue": 383285,
        "revenue_growth_yoy": 15.2,
        "earnings_per_share": 6.13,
        "pe_ratio": 28.5,
        "profit_margin": 25.3,
        "recent_news": [
            "Apple announces new iPhone 16",
            "Q4 earnings beat expectations",
            "New AI features rolling out",
        ],
        "recent_press_releases": [
            "Apple announces Vision Pro availability",
        ],
        "catalyst_events": [
            "iPhone 16 launch September 2025",
            "Q1 2026 earnings call scheduled",
        ],
        "analyst_rating": "Buy",
        "price_target": 220.0,
        "analyst_count": 45,
        "sources": [
            "https://www.sec.gov/...",
            "https://finance.yahoo.com/...",
            "https://www.apple.com/newsroom/",
        ],
        "search_queries_used": [
            "AAPL company profile",
            "Apple financial metrics 2025",
            "Apple recent news",
        ],
        "confidence": 0.95,
    }


@pytest.fixture
def sample_company_data():
    """Sample CompanyData for testing."""
    return CompanyData(
        ticker="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        market_cap=2800000,
        revenue=383285,
        revenue_growth_yoy=15.2,
        analyst_rating="Buy",
        price_target=220.0,
        sources=["https://example.com"],
        confidence=0.95,
    )


class TestCompanyAdapter:
    """Tests for CompanyAdapter class."""

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_get_company_data_success(self, mock_config, mock_openai_class, mock_company_response):
        """Test successful company data retrieval."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(mock_company_response)))]
        )

        # Execute
        adapter = CompanyAdapter()
        company_data = adapter.get_company_data("AAPL")

        # Assert
        assert company_data.ticker == "AAPL"
        assert company_data.company_name == "Apple Inc."
        assert company_data.sector == "Technology"
        assert company_data.market_cap == 2800000
        assert company_data.revenue_growth_yoy == 15.2
        assert company_data.analyst_rating == "Buy"
        assert company_data.confidence == 0.95
        assert len(company_data.recent_news) == 3
        assert len(company_data.catalyst_events) == 2

        # Verify OpenAI was called
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["temperature"] == 0.2
        assert call_kwargs["timeout"] == 30.0

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    @patch("src.datasources.company.Cache")
    def test_get_company_data_uses_cache(
        self, mock_cache_class, mock_config, mock_openai_class, sample_company_data
    ):
        """Test that cached data is returned without API call."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_cache = Mock()
        mock_cache_class.return_value = mock_cache

        # Return cached data
        mock_cache.get.return_value = {
            "ticker": "AAPL",
            "company_name": "Apple Inc.",
            "sector": "Technology",
            "industry": None,
            "market_cap": 2800000,
            "revenue": None,
            "revenue_growth_yoy": 15.2,
            "earnings_per_share": None,
            "pe_ratio": None,
            "profit_margin": None,
            "recent_news": [],
            "recent_press_releases": [],
            "catalyst_events": [],
            "analyst_rating": "Buy",
            "price_target": 220.0,
            "analyst_count": None,
            "description": None,
            "employees": None,
            "founded_year": None,
            "headquarters": None,
            "sources": [],
            "search_queries_used": [],
            "researched_at": datetime.now().isoformat(),
            "confidence": 0.95,
            "attribution": {
                "source": "chatbot_research",
                "timestamp": datetime.now().isoformat(),
                "url": None,
                "api_endpoint": "openai/chat/completions",
                "version": "1.0",
            },
        }

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Execute
        adapter = CompanyAdapter()
        company_data = adapter.get_company_data("AAPL")

        # Assert - data was returned from cache
        assert company_data.ticker == "AAPL"
        assert company_data.company_name == "Apple Inc."

        # OpenAI should NOT be called
        mock_client.chat.completions.create.assert_not_called()

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_get_company_data_api_error(self, mock_config, mock_openai_class):
        """Test handling of API errors."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.side_effect = Exception("API timeout")

        # Execute
        adapter = CompanyAdapter()
        company_data = adapter.get_company_data("AAPL")

        # Assert - should return minimal fallback data
        assert company_data.ticker == "AAPL"
        assert company_data.company_name == "AAPL"  # Fallback uses ticker as name
        assert company_data.confidence == 0.0
        assert len(company_data.sources) == 0

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_get_company_data_invalid_json(self, mock_config, mock_openai_class):
        """Test handling of invalid JSON response."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client

        # Create properly nested mock response with invalid JSON
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "invalid json"
        mock_client.chat.completions.create.return_value = mock_response

        # Execute
        adapter = CompanyAdapter()
        company_data = adapter.get_company_data("AAPL")

        # Assert - should return fallback data
        assert company_data.ticker == "AAPL"
        assert company_data.company_name == "AAPL"  # Fallback uses ticker as name
        assert company_data.confidence == 0.0

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_fetch_method(self, mock_config, mock_openai_class, mock_company_response):
        """Test the fetch() method (DataAdapterProtocol implementation)."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(mock_company_response)))]
        )

        # Execute
        adapter = CompanyAdapter()
        company_data = adapter.fetch("AAPL")

        # Assert
        assert isinstance(company_data, CompanyData)
        assert company_data.ticker == "AAPL"

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_get_attribution(self, mock_config, mock_openai_class, mock_company_response):
        """Test get_attribution() method."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(mock_company_response)))]
        )

        # Execute
        adapter = CompanyAdapter()
        adapter.get_company_data("AAPL")
        attribution = adapter.get_attribution()

        # Assert
        assert isinstance(attribution, Attribution)
        assert attribution.source == DataSource.CHATBOT_RESEARCH
        assert attribution.api_endpoint == "openai/chat/completions"

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_get_attribution_no_fetch_raises_error(self, mock_config, mock_openai_class):
        """Test that get_attribution() raises error if no fetch performed."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        # Execute
        adapter = CompanyAdapter()

        # Assert
        with pytest.raises(ValueError, match="No fetch performed yet"):
            adapter.get_attribution()

    @patch("src.datasources.company.OpenAI")
    @patch("src.datasources.company.get_config")
    def test_ticker_normalization(self, mock_config, mock_openai_class, mock_company_response):
        """Test that ticker symbols are normalized to uppercase."""
        # Setup
        mock_config.return_value.llm.openai_api_key = "test-key"
        mock_config.return_value.llm.model_fact_checker = "gpt-4o"
        mock_config.return_value.datasources.cache.cache_dir = "data/cache"

        mock_client = Mock()
        mock_openai_class.return_value = mock_client
        mock_client.chat.completions.create.return_value = Mock(
            choices=[Mock(message=Mock(content=json.dumps(mock_company_response)))]
        )

        # Execute - lowercase ticker
        adapter = CompanyAdapter()
        company_data = adapter.get_company_data("aapl")

        # Assert - should be normalized to uppercase
        assert company_data.ticker == "AAPL"


class TestCompanyData:
    """Tests for CompanyData dataclass."""

    def test_company_data_creation(self):
        """Test CompanyData creation with required fields."""
        # Execute
        company_data = CompanyData(
            ticker="AAPL",
            company_name="Apple Inc.",
        )

        # Assert
        assert company_data.ticker == "AAPL"
        assert company_data.company_name == "Apple Inc."
        assert company_data.sector is None
        assert company_data.recent_news == []
        assert company_data.sources == []
        assert company_data.confidence == 0.0

    def test_company_data_with_all_fields(self, sample_company_data):
        """Test CompanyData with all fields populated."""
        # Assert
        assert sample_company_data.ticker == "AAPL"
        assert sample_company_data.company_name == "Apple Inc."
        assert sample_company_data.sector == "Technology"
        assert sample_company_data.market_cap == 2800000
        assert sample_company_data.revenue_growth_yoy == 15.2
        assert sample_company_data.analyst_rating == "Buy"
        assert sample_company_data.confidence == 0.95
