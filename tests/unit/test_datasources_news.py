"""Tests for news and sentiment adapter with REAL API calls.

These tests make actual calls to Yahoo Finance news API to ensure real-world functionality.
They may be slower than mocked tests but provide better confidence in the integration.
"""

import time

import pytest

from src.datasources.base import DataNotFoundError, DataSource
from src.datasources.cache import Cache
from src.datasources.news import NewsAdapter, NewsDataError


@pytest.fixture
def temp_cache(tmp_path):
    """Create a temporary cache for testing."""
    cache_dir = tmp_path / "test_cache"
    return Cache(cache_dir=cache_dir, ttl_seconds=3600)


@pytest.fixture
def adapter(temp_cache):
    """Create a NewsAdapter with temporary cache."""
    return NewsAdapter(cache=temp_cache)


class TestNewsAdapterInitialization:
    """Test NewsAdapter initialization."""

    def test_create_adapter_with_cache(self, temp_cache):
        """Test creating adapter with provided cache."""
        adapter = NewsAdapter(cache=temp_cache)
        assert adapter.source == DataSource.YAHOO_FINANCE
        assert adapter.cache is temp_cache

    def test_create_adapter_without_cache(self):
        """Test creating adapter creates default cache."""
        adapter = NewsAdapter()
        assert adapter.source == DataSource.YAHOO_FINANCE
        assert adapter.cache is not None
        assert adapter.cache.ttl_seconds == 3600  # 1 hour default


class TestGetHeadlines:
    """Test get_headlines method with real API calls."""

    def test_get_headlines_aapl(self, adapter):
        """Test fetching headlines for AAPL (real API call)."""
        headlines = adapter.get_headlines("AAPL", max_age_days=7, limit=10)

        assert isinstance(headlines, list)
        assert len(headlines) > 0

        # Check first headline structure
        headline = headlines[0]
        assert "title" in headline
        assert "summary" in headline
        assert "published_at" in headline
        assert "url" in headline
        assert "provider" in headline

        # Verify title is not empty
        assert len(headline["title"]) > 0

    def test_get_headlines_multiple_tickers(self, adapter):
        """Test fetching headlines for multiple tickers."""
        tickers = ["MSFT", "GOOGL"]

        for ticker in tickers:
            headlines = adapter.get_headlines(ticker, max_age_days=7, limit=5)
            assert len(headlines) > 0
            assert all("title" in h for h in headlines)
            time.sleep(0.5)  # Be nice to the API

    def test_get_headlines_caching(self, adapter):
        """Test that headlines are cached on second call."""
        # First call - should fetch from API
        headlines1 = adapter.get_headlines("AAPL", max_age_days=7)

        # Second call - should use cache
        start = time.time()
        headlines2 = adapter.get_headlines("AAPL", max_age_days=7)
        elapsed = time.time() - start

        # Should be nearly instant from cache
        assert elapsed < 0.1
        assert len(headlines2) == len(headlines1)
        assert headlines2[0]["title"] == headlines1[0]["title"]

    def test_get_headlines_invalid_ticker(self, adapter):
        """Test fetching headlines for invalid ticker raises error."""
        with pytest.raises((DataNotFoundError, NewsDataError)):
            adapter.get_headlines("INVALID_TICKER_XYZ_9999", max_age_days=7)

    def test_get_headlines_attribution(self, adapter):
        """Test that attribution is properly set."""
        adapter.get_headlines("AAPL", max_age_days=7)
        attr = adapter.get_attribution()

        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.url is not None
        assert "AAPL" in attr.url
        assert attr.metadata.get("ticker") == "AAPL"

    def test_get_headlines_limit(self, adapter):
        """Test that limit parameter works."""
        headlines = adapter.get_headlines("AAPL", max_age_days=7, limit=3)
        # Should get at most 3 headlines (could be less if not enough recent news)
        assert len(headlines) <= 3


class TestGetSentiment:
    """Test get_sentiment method."""

    def test_sentiment_positive_text(self, adapter):
        """Test sentiment analysis on positive text."""
        text = "Apple stock soars on strong earnings beat, shares surge to record high"
        sentiment = adapter.get_sentiment(text)

        assert "score" in sentiment
        assert "label" in sentiment
        assert "positive_words" in sentiment
        assert "negative_words" in sentiment
        assert "risk_keywords" in sentiment

        # Should be positive
        assert sentiment["score"] > 0
        assert sentiment["label"] == "positive"
        assert len(sentiment["positive_words"]) > 0

    def test_sentiment_negative_text(self, adapter):
        """Test sentiment analysis on negative text."""
        text = "Company faces fraud investigation, stock plunges on disappointing earnings"
        sentiment = adapter.get_sentiment(text)

        # Should be negative
        assert sentiment["score"] < 0
        assert sentiment["label"] == "negative"
        assert len(sentiment["negative_words"]) > 0 or len(sentiment["risk_keywords"]) > 0

    def test_sentiment_neutral_text(self, adapter):
        """Test sentiment analysis on neutral text."""
        text = "Company announces quarterly results, stock price remains stable"
        sentiment = adapter.get_sentiment(text)

        # Should be neutral or close to it
        assert -0.5 < sentiment["score"] < 0.5
        # Label could be neutral or slight positive/negative
        assert sentiment["label"] in ["positive", "negative", "neutral"]

    def test_sentiment_risk_keywords(self, adapter):
        """Test that risk keywords are detected."""
        text = "Company under investigation for fraud, faces lawsuit over data breach"
        sentiment = adapter.get_sentiment(text)

        assert len(sentiment["risk_keywords"]) > 0
        assert "fraud" in sentiment["risk_keywords"] or "lawsuit" in sentiment["risk_keywords"]
        # Risk keywords should make sentiment negative
        assert sentiment["score"] < 0

    def test_sentiment_score_range(self, adapter):
        """Test that sentiment score is always in valid range."""
        test_texts = [
            "very strong buy upgrade bullish surge soar rally",  # Very positive
            "bankruptcy fraud lawsuit scandal crisis downgrade",  # Very negative
            "announcement today meeting scheduled",  # Neutral
        ]

        for text in test_texts:
            sentiment = adapter.get_sentiment(text)
            assert -1.0 <= sentiment["score"] <= 1.0


class TestAnalyzeHeadlines:
    """Test analyze_headlines method with real API calls."""

    def test_analyze_headlines_aapl(self, adapter):
        """Test analyzing headlines for AAPL."""
        analysis = adapter.analyze_headlines("AAPL", max_age_days=7, limit=10)

        assert "headlines" in analysis
        assert "sentiment" in analysis
        assert "risk_detected" in analysis
        assert "risk_keywords" in analysis

        # Check headlines
        assert len(analysis["headlines"]) > 0

        # Check sentiment
        assert "score" in analysis["sentiment"]
        assert "label" in analysis["sentiment"]
        assert -1.0 <= analysis["sentiment"]["score"] <= 1.0

        # Check risk detection
        assert isinstance(analysis["risk_detected"], bool)
        assert isinstance(analysis["risk_keywords"], list)

    def test_analyze_headlines_multiple_tickers(self, adapter):
        """Test analyzing headlines for multiple tickers."""
        tickers = ["MSFT", "GOOGL"]

        for ticker in tickers:
            analysis = adapter.analyze_headlines(ticker, max_age_days=7, limit=5)
            assert len(analysis["headlines"]) > 0
            assert "score" in analysis["sentiment"]
            time.sleep(0.5)

    def test_analyze_headlines_caching(self, adapter):
        """Test that analysis is cached."""
        # First call
        analysis1 = adapter.analyze_headlines("AAPL", max_age_days=7)

        # Second call - headlines should be cached
        start = time.time()
        analysis2 = adapter.analyze_headlines("AAPL", max_age_days=7)
        elapsed = time.time() - start

        # Should be fast from cache
        assert elapsed < 0.2  # Slightly longer because sentiment is recalculated
        assert len(analysis2["headlines"]) == len(analysis1["headlines"])


class TestCacheIntegration:
    """Test cache integration."""

    def test_cache_keys_are_unique(self, adapter):
        """Test that different requests use different cache keys."""
        # Fetch with different parameters
        adapter.get_headlines("AAPL", max_age_days=7)
        adapter.get_headlines("AAPL", max_age_days=3)
        adapter.get_headlines("MSFT", max_age_days=7)

        # Check cache has multiple entries
        stats = adapter.cache.get_stats()
        assert stats["total_entries"] >= 3

    def test_cache_persists_across_instances(self, temp_cache):
        """Test that cache persists across adapter instances."""
        # First adapter
        adapter1 = NewsAdapter(cache=temp_cache)
        headlines1 = adapter1.get_headlines("AAPL", max_age_days=7)

        # Second adapter with same cache
        adapter2 = NewsAdapter(cache=temp_cache)
        start = time.time()
        headlines2 = adapter2.get_headlines("AAPL", max_age_days=7)
        elapsed = time.time() - start

        # Should be instant from cache
        assert elapsed < 0.1
        assert len(headlines2) == len(headlines1)


class TestErrorHandling:
    """Test error handling."""

    def test_invalid_ticker_raises_appropriate_error(self, adapter):
        """Test that invalid tickers raise appropriate errors."""
        with pytest.raises((DataNotFoundError, NewsDataError)):
            adapter.get_headlines("NOT_A_REAL_TICKER_12345", max_age_days=7)

    def test_fetch_method_not_implemented(self, adapter):
        """Test that generic fetch() raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            adapter.fetch()


class TestRealWorldUsage:
    """Test real-world usage scenarios."""

    def test_news_sentiment_workflow(self, adapter):
        """Test a realistic workflow of fetching and analyzing news."""
        # Get headlines
        headlines = adapter.get_headlines("AAPL", max_age_days=7, limit=10)
        assert len(headlines) > 0

        # Analyze each headline individually
        sentiments = []
        risk_flags = []

        for headline in headlines[:5]:  # Just analyze first 5
            text = f"{headline['title']} {headline['summary']}"
            sentiment = adapter.get_sentiment(text)
            sentiments.append(sentiment["score"])

            has_risk = len(sentiment["risk_keywords"]) > 0
            risk_flags.append(has_risk)

        # Calculate average sentiment
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0
        risk_detected = any(risk_flags)

        # Verify we got reasonable results
        assert -1.0 <= avg_sentiment <= 1.0
        assert isinstance(risk_detected, bool)

    def test_compare_tickers_sentiment(self, adapter):
        """Test comparing sentiment across tickers."""
        tickers = ["AAPL", "MSFT"]
        results = {}

        for ticker in tickers:
            analysis = adapter.analyze_headlines(ticker, max_age_days=7, limit=10)
            results[ticker] = {
                "sentiment_score": analysis["sentiment"]["score"],
                "sentiment_label": analysis["sentiment"]["label"],
                "risk_detected": analysis["risk_detected"],
                "headline_count": len(analysis["headlines"]),
            }
            time.sleep(0.5)

        # Verify we got results for both
        assert len(results) == 2
        for _ticker, data in results.items():
            assert -1.0 <= data["sentiment_score"] <= 1.0
            assert data["sentiment_label"] in ["positive", "negative", "neutral"]
            assert data["headline_count"] > 0

    def test_risk_detection_workflow(self, adapter):
        """Test risk detection in news headlines."""
        # Analyze headlines
        analysis = adapter.analyze_headlines("AAPL", max_age_days=7, limit=10)

        # Check risk detection structure
        assert isinstance(analysis["risk_detected"], bool)
        assert isinstance(analysis["risk_keywords"], list)

        if analysis["risk_detected"]:
            # If risk detected, should have keywords
            assert len(analysis["risk_keywords"]) > 0
            # And sentiment should likely be negative
            # (though not guaranteed - could have mixed news)
        else:
            # If no risk detected, keywords should be empty
            assert len(analysis["risk_keywords"]) == 0


class TestSentimentKeywords:
    """Test sentiment keyword matching."""

    def test_positive_keywords_detected(self, adapter):
        """Test that positive keywords are correctly identified."""
        text = "Stock surges on strong earnings, company outperforms expectations"
        sentiment = adapter.get_sentiment(text)

        assert len(sentiment["positive_words"]) > 0
        assert sentiment["score"] > 0

    def test_negative_keywords_detected(self, adapter):
        """Test that negative keywords are correctly identified."""
        text = "Stock plunges on disappointing results, company underperforms"
        sentiment = adapter.get_sentiment(text)

        assert len(sentiment["negative_words"]) > 0
        assert sentiment["score"] < 0

    def test_risk_keywords_count_double(self, adapter):
        """Test that risk keywords have stronger negative impact."""
        # Text with just negative words
        text1 = "Stock falls on weak results"
        sentiment1 = adapter.get_sentiment(text1)

        # Text with risk keywords
        text2 = "Stock under fraud investigation"
        sentiment2 = adapter.get_sentiment(text2)

        # Risk keywords should have stronger negative impact
        assert sentiment2["score"] <= sentiment1["score"]
