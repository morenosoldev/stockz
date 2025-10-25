"""News and sentiment data adapter.

This module provides news headline fetching and sentiment analysis
using Yahoo Finance news (via yfinance) - no API key required.

Features:
- Fetch news headlines by ticker
- Simple sentiment analysis (positive/negative/neutral)
- Risk keyword detection
- Full attribution tracking
- Intelligent caching (shorter TTL than prices)
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import yfinance as yf

from src.datasources.attribution import create_attribution
from src.datasources.base import (
    Attribution,
    BaseDataAdapter,
    DataNotFoundError,
    DataSource,
)
from src.datasources.cache import Cache

# Risk keywords that indicate potential problems
RISK_KEYWORDS = {
    "bankruptcy",
    "bankrupt",
    "fraud",
    "fraudulent",
    "investigation",
    "investigated",
    "lawsuit",
    "sued",
    "recall",
    "recalled",
    "scandal",
    "crisis",
    "layoff",
    "layoffs",
    "downgrade",
    "warning",
    "warned",
    "fine",
    "fined",
    "penalty",
    "penalized",
    "violation",
    "violated",
    "breach",
    "breached",
    "hack",
    "hacked",
    "cyberattack",
    "data breach",
    "loss",
    "losses",
    "decline",
    "declined",
    "disappointing",
    "missed",
    "miss",
    "weak",
    "weaker",
    "concern",
    "concerns",
    "worried",
    "worry",
    "risk",
    "risks",
    "threat",
    "threatens",
}

# Positive sentiment words
POSITIVE_WORDS = {
    "surge",
    "surges",
    "soar",
    "soars",
    "rally",
    "rallies",
    "gain",
    "gains",
    "beat",
    "beats",
    "exceed",
    "exceeds",
    "strong",
    "stronger",
    "upgrade",
    "upgraded",
    "bullish",
    "positive",
    "optimistic",
    "buy",
    "buying",
    "growth",
    "growing",
    "innovation",
    "innovative",
    "record",
    "high",
    "peak",
    "best",
    "improve",
    "improved",
    "improvement",
    "outperform",
    "outperforms",
    "win",
    "wins",
    "success",
    "successful",
}

# Negative sentiment words (beyond risk keywords)
NEGATIVE_WORDS = {
    "fall",
    "falls",
    "drop",
    "drops",
    "plunge",
    "plunges",
    "tumble",
    "tumbles",
    "sell",
    "selling",
    "bearish",
    "negative",
    "pessimistic",
    "low",
    "worst",
    "bad",
    "poor",
    "underperform",
    "underperforms",
    "lose",
    "loses",
    "fail",
    "fails",
    "failure",
}


class NewsDataError(Exception):
    """Exception raised for news data errors."""

    pass


class NewsAdapter(BaseDataAdapter):
    """News and sentiment data adapter using Yahoo Finance.

    Provides news headlines and simple sentiment analysis for tickers.
    Uses yfinance for news data (no API key required).

    Attributes:
        source: DataSource.YAHOO_FINANCE (news from Yahoo Finance)
        cache: Cache instance for storing fetched data
        logger: Structured logger instance
    """

    source = DataSource.YAHOO_FINANCE

    def __init__(self, cache: Cache | None = None):
        """Initialize NewsAdapter.

        Args:
            cache: Optional Cache instance. If not provided, creates default cache
                  with 1-hour TTL (news changes more frequently than prices).
        """
        if cache is None:
            cache = Cache(ttl_seconds=3600)  # 1 hour default for news

        super().__init__()
        self.cache = cache
        self.logger.info(
            "NewsAdapter initialized",
            cache_dir=str(cache.cache_dir),
            cache_ttl=cache.ttl_seconds,
            source=self.source.value,
        )

    def get_headlines(
        self,
        ticker: str,
        max_age_days: int = 7,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch news headlines for a ticker.

        Args:
            ticker: Stock ticker symbol (e.g., "AAPL")
            max_age_days: Maximum age of headlines in days (default: 7)
            limit: Maximum number of headlines to return (default: 10)

        Returns:
            List of headline dictionaries with:
                - title: Headline text
                - summary: Article summary/description
                - published_at: Publication timestamp (ISO 8601)
                - url: Link to full article
                - provider: News source name

        Raises:
            DataNotFoundError: If ticker is invalid or has no news
            NewsDataError: If news cannot be fetched

        Example:
            >>> adapter = NewsAdapter()
            >>> headlines = adapter.get_headlines("AAPL", max_age_days=7)
            >>> assert len(headlines) > 0
            >>> assert "title" in headlines[0]
        """
        # Check cache first
        cache_key = {"ticker": ticker, "max_age_days": max_age_days, "limit": limit}
        cached = self.cache.get(cache_key)
        if cached is not None:
            self.logger.debug("Cache hit for headlines", ticker=ticker)
            self._last_attribution = cached["attribution"]
            headlines_data: list[dict[str, Any]] = cached["data"]
            return headlines_data

        # Fetch from Yahoo Finance
        self.logger.info(
            "Fetching headlines",
            ticker=ticker,
            max_age_days=max_age_days,
            limit=limit,
        )

        try:
            stock = yf.Ticker(ticker)
            news = stock.news

            if not news:
                raise DataNotFoundError(
                    f"No news found for ticker {ticker}",
                    source=self.source,
                )

            # Filter and transform headlines
            cutoff_date = datetime.now(UTC) - timedelta(days=max_age_days)
            headlines = []

            for item in news[:limit]:
                content = item.get("content", {})

                # Parse publication date
                pub_date_str = content.get("pubDate")
                if pub_date_str:
                    pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                else:
                    pub_date = datetime.now(UTC)

                # Skip if too old
                if pub_date < cutoff_date:
                    continue

                # Extract headline data
                headline = {
                    "title": content.get("title", ""),
                    "summary": content.get("summary", ""),
                    "published_at": pub_date.isoformat(),
                    "url": content.get("canonicalUrl", {}).get("url", ""),
                    "provider": content.get("provider", {}).get("displayName", "Yahoo Finance"),
                }

                headlines.append(headline)

            if not headlines:
                raise DataNotFoundError(
                    f"No recent news found for ticker {ticker} (within {max_age_days} days)",
                    source=self.source,
                )

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://finance.yahoo.com/quote/{ticker}/news",
                ticker=ticker,
                headlines_count=len(headlines),
                max_age_days=max_age_days,
            )

            # Cache the result (1 hour TTL for news)
            self.cache.set(
                cache_key,
                {"data": headlines, "attribution": self._last_attribution},
                ttl_seconds=3600,  # 1 hour
                metadata={"ticker": ticker, "count": len(headlines)},
            )

            self.logger.info(
                "Headlines fetched successfully",
                ticker=ticker,
                count=len(headlines),
                newest=headlines[0]["published_at"] if headlines else None,
            )

            return headlines

        except DataNotFoundError:
            # Re-raise as-is
            raise
        except Exception as e:
            raise NewsDataError(
                f"Failed to fetch news for {ticker}: {e}",
            ) from e

    def get_sentiment(self, text: str) -> dict[str, Any]:
        """Analyze sentiment of text (simple rule-based).

        Uses simple word counting approach:
        - Counts positive, negative, and risk keywords
        - Returns score from -1 (very negative) to +1 (very positive)
        - Neutral is around 0

        Args:
            text: Text to analyze (headline, summary, or combined)

        Returns:
            Dictionary with:
                - score: Sentiment score from -1 to +1
                - label: "positive", "negative", or "neutral"
                - positive_words: List of matched positive words
                - negative_words: List of matched negative words
                - risk_keywords: List of matched risk keywords

        Example:
            >>> adapter = NewsAdapter()
            >>> sentiment = adapter.get_sentiment("Apple stock soars on strong earnings")
            >>> assert sentiment["score"] > 0
            >>> assert sentiment["label"] == "positive"
        """
        text_lower = text.lower()

        # Find matched words
        positive_matches = [word for word in POSITIVE_WORDS if word in text_lower]
        negative_matches = [word for word in NEGATIVE_WORDS if word in text_lower]
        risk_matches = [word for word in RISK_KEYWORDS if word in text_lower]

        # Calculate score
        positive_count = len(positive_matches)
        negative_count = len(negative_matches)
        risk_count = len(risk_matches)

        # Risk keywords count double as negative
        total_positive = positive_count
        total_negative = negative_count + (risk_count * 2)

        # Normalize to -1 to +1
        total = total_positive + total_negative
        if total == 0:
            score = 0.0
            label = "neutral"
        else:
            score = (total_positive - total_negative) / max(total, 1)
            # Clamp to -1 to +1
            score = max(-1.0, min(1.0, score))

            if score > 0.2:
                label = "positive"
            elif score < -0.2:
                label = "negative"
            else:
                label = "neutral"

        return {
            "score": score,
            "label": label,
            "positive_words": positive_matches,
            "negative_words": negative_matches,
            "risk_keywords": risk_matches,
        }

    def analyze_headlines(
        self,
        ticker: str,
        max_age_days: int = 7,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Fetch headlines and analyze sentiment.

        Convenience method that combines get_headlines() and get_sentiment().

        Args:
            ticker: Stock ticker symbol
            max_age_days: Maximum age of headlines in days
            limit: Maximum number of headlines to analyze

        Returns:
            Dictionary with:
                - headlines: List of headline dictionaries
                - sentiment: Overall sentiment analysis
                - risk_detected: Boolean indicating if risk keywords found
                - risk_keywords: List of all unique risk keywords found

        Example:
            >>> adapter = NewsAdapter()
            >>> analysis = adapter.analyze_headlines("AAPL")
            >>> assert "headlines" in analysis
            >>> assert "sentiment" in analysis
            >>> assert "risk_detected" in analysis
        """
        headlines = self.get_headlines(ticker, max_age_days, limit)

        # Combine all text for sentiment analysis
        combined_text = " ".join(
            [f"{h.get('title', '')} {h.get('summary', '')}" for h in headlines]
        )

        sentiment = self.get_sentiment(combined_text)

        # Check for risk keywords
        all_risk_keywords = set()
        for headline in headlines:
            headline_text = f"{headline.get('title', '')} {headline.get('summary', '')}"
            headline_sentiment = self.get_sentiment(headline_text)
            all_risk_keywords.update(headline_sentiment["risk_keywords"])

        risk_detected = len(all_risk_keywords) > 0

        self.logger.info(
            "Headlines analyzed",
            ticker=ticker,
            count=len(headlines),
            sentiment_score=sentiment["score"],
            sentiment_label=sentiment["label"],
            risk_detected=risk_detected,
            risk_keywords_count=len(all_risk_keywords),
        )

        return {
            "headlines": headlines,
            "sentiment": sentiment,
            "risk_detected": risk_detected,
            "risk_keywords": list(all_risk_keywords),
        }

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Generic fetch method (delegates to specific methods).

        This implements the DataAdapterProtocol interface.
        Use specific methods (get_headlines, analyze_headlines) instead.

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Fetched data

        Raises:
            NotImplementedError: Always (use specific methods)
        """
        raise NotImplementedError("Use get_headlines() or analyze_headlines() instead of fetch()")

    def _build_attribution(
        self,
        **metadata: Any,
    ) -> Attribution:
        """Build attribution for fetched data.

        Args:
            **metadata: Additional metadata (including optional 'url')

        Returns:
            Attribution object
        """
        return create_attribution(
            source=self.source,
            version="1.0",
            **metadata,
        )
