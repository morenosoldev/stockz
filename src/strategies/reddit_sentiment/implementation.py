from datetime import date
from typing import Any

from src.datasources.aggregation import aggregate_ticker_sentiments
from src.datasources.reddit import RedditAdapter
from src.datasources.sentiment import SentimentAnalyzer
from src.ops.logging import get_logger

from ..base import BaseStrategy, StrategyConfig

logger = get_logger(__name__)


class RedditSentimentStrategy(BaseStrategy):
    """Reddit sentiment-based strategy.

    This strategy uses Reddit discussion sentiment to identify candidates.
    Unlike price-based strategies, it fetches Reddit data once and filters
    the ticker universe based on sentiment scores.

    This strategy does NOT require price data from Yahoo Finance.
    """

    # Class attribute to signal pipeline to skip price fetching
    requires_price_data = False

    # Class attribute to signal scanner to use get_universe() instead of S&P 500
    provides_own_universe = True

    def __init__(self, config: StrategyConfig | None = None):
        """Initialize strategy with configuration.

        Args:
            config: Strategy configuration from config.yml
        """
        # Define name and version before calling super().__init__
        # This is required because BaseStrategy.__init__ accesses self.name
        self._name = "reddit"
        self._version = "1.0.0"

        # Use default config if not provided
        if config is None:
            config = StrategyConfig(
                name=self._name,
                version=self._version,
                description="Reddit sentiment-based candidate selection",
                enabled=True,
                parameters={
                    "sentiment_threshold": 0.5,
                    "top_n": 20,
                    "subreddit": "wallstreetbets",
                    "post_limit": 100,
                    "min_mentions": 2,
                    "min_confidence": 0.6,
                },
            )

        super().__init__(config)

        # Extract parameters
        params = config.parameters
        self.sentiment_threshold = params.get("sentiment_threshold", 0.5)
        self.top_n = params.get("top_n", 20)

        # Support both single subreddit (legacy) and multiple subreddits (new)
        if "subreddits" in params:
            self.subreddits = params["subreddits"]
        else:
            # Legacy support: single subreddit parameter
            self.subreddits = [params.get("subreddit", "wallstreetbets")]

        self.posts_per_subreddit = params.get("posts_per_subreddit", 50)
        self.min_mentions = params.get("min_mentions", 3)
        self.min_confidence = params.get("min_confidence", 0.6)
        self.min_comment_score = params.get("min_comment_score", 5)
        self.require_catalysts = params.get("require_catalysts", False)
        self.cross_subreddit_boost = params.get("cross_subreddit_boost", 0.1)

        # Initialize adapters (lazy load to avoid API calls during registration)
        self._reddit_adapter: RedditAdapter | None = None
        self._sentiment_analyzer: SentimentAnalyzer | None = None
        self._sentiment_cache: dict[str, float] = {}
        self._mentions_cache: dict[str, int] = {}
        self._rationale_cache: dict[str, dict[str, Any]] = {}  # Store detailed LLM rationale
        self._cache_date: date | None = None

    @property
    def name(self) -> str:
        """Strategy identifier."""
        return self._name

    @property
    def version(self) -> str:
        """Strategy version."""
        return self._version

    @property
    def reddit_adapter(self) -> RedditAdapter:
        """Lazy-load Reddit adapter."""
        if self._reddit_adapter is None:
            self._reddit_adapter = RedditAdapter(cache_enabled=True)
        return self._reddit_adapter

    @property
    def sentiment_analyzer(self) -> SentimentAnalyzer:
        """Lazy-load sentiment analyzer."""
        if self._sentiment_analyzer is None:
            self._sentiment_analyzer = SentimentAnalyzer(cache_enabled=True)
        return self._sentiment_analyzer

    def _refresh_sentiment_data(self, asof: date) -> None:
        """Refresh sentiment data from multiple Reddit subreddits (called once per scan).

        Args:
            asof: Date to fetch data for
        """
        # Only fetch if cache is stale
        if self._cache_date == asof and self._sentiment_cache:
            logger.info("Using cached Reddit sentiment data", date=str(asof))
            return

        subreddit_list = ", ".join([f"r/{sub}" for sub in self.subreddits[:3]])
        if len(self.subreddits) > 3:
            subreddit_list += f" (+{len(self.subreddits) - 3} more)"

        logger.info(
            f"📡 Fetching {self.posts_per_subreddit} posts from each of {len(self.subreddits)} subreddits: {subreddit_list}",
            subreddits=self.subreddits,
            posts_per_sub=self.posts_per_subreddit,
            date=str(asof),
        )

        # Fetch posts from all subreddits
        all_posts = []
        subreddit_mentions: dict[str, set[str]] = {}  # Track which subreddits mentioned each ticker

        for subreddit in self.subreddits:
            try:
                logger.info(f"  📥 Fetching from r/{subreddit}...", subreddit=subreddit)

                posts = self.reddit_adapter.fetch_hot_posts(
                    subreddit=subreddit,
                    limit=self.posts_per_subreddit,
                    include_comments=True,
                    comments_limit=20,
                )

                # Track which tickers were mentioned in which subreddits
                for post in posts:
                    for ticker in post.get("tickers", []):
                        if ticker not in subreddit_mentions:
                            subreddit_mentions[ticker] = set()
                        subreddit_mentions[ticker].add(subreddit)

                all_posts.extend(posts)

                logger.info(
                    f"  ✅ Fetched {len(posts)} posts from r/{subreddit}",
                    subreddit=subreddit,
                    posts_count=len(posts),
                )
            except Exception as e:
                logger.warning(
                    f"  ⚠️ Failed to fetch from r/{subreddit}: {e}",
                    subreddit=subreddit,
                    error=str(e),
                )
                continue

        logger.info(
            f"✅ Total: {len(all_posts)} posts fetched from {len(self.subreddits)} subreddits",
            total_posts=len(all_posts),
            subreddit_count=len(self.subreddits),
        )

        logger.info("🤖 Analyzing sentiment for tickers mentioned in posts and comments...")

        # Analyze sentiment (including comments)
        sentiment_results = self.sentiment_analyzer.analyze_batch(
            all_posts, analyze_comments=True, min_comment_score=self.min_comment_score
        )

        logger.info(
            f"✅ Sentiment analysis complete - found {len(sentiment_results)} ticker mentions",
            ticker_mentions=len(sentiment_results),
        )

        logger.info(
            f"📊 Aggregating and filtering candidates (min {self.min_mentions} mentions, min {self.sentiment_threshold:.1f} score)..."
        )

        # Aggregate with quality filters
        aggregated = aggregate_ticker_sentiments(
            sentiment_results,
            min_mentions=self.min_mentions,
            min_confidence=self.min_confidence,
            min_weighted_score=self.sentiment_threshold,
        )

        # Apply cross-subreddit boost and catalyst filtering
        for item in aggregated:
            ticker = item["ticker"]

            # Boost score if mentioned across multiple subreddits
            num_subs = len(subreddit_mentions.get(ticker, set()))
            if num_subs > 1:
                boost = (num_subs - 1) * self.cross_subreddit_boost
                item["weighted_score"] = min(1.0, item["weighted_score"] + boost)
                item["subreddit_count"] = num_subs
                item["subreddits"] = list(subreddit_mentions.get(ticker, set()))
                logger.info(
                    f"  🔥 ${ticker} mentioned in {num_subs} subreddits - score boosted by {boost:+.2f}",
                    ticker=ticker,
                    subreddits=num_subs,
                    boost=boost,
                )
            else:
                item["subreddit_count"] = 1
                item["subreddits"] = list(subreddit_mentions.get(ticker, set()))

            # Filter by catalysts if required
            if self.require_catalysts:
                catalysts = item.get("llm_rationale", {}).get("catalysts", [])
                if not catalysts:
                    logger.info(
                        f"  ❌ ${ticker} filtered out - no catalysts mentioned", ticker=ticker
                    )
                    item["filtered"] = True

        # Remove filtered items
        if self.require_catalysts:
            aggregated = [item for item in aggregated if not item.get("filtered", False)]

        # Build cache with detailed rationale and metadata
        self._sentiment_cache = {item["ticker"]: item["weighted_score"] for item in aggregated}
        self._mentions_cache = {item["ticker"]: item["mentions"] for item in aggregated}
        self._rationale_cache = {
            item["ticker"]: {
                **item.get("llm_rationale", {}),
                "subreddit_count": item.get("subreddit_count", 1),
                "subreddits": item.get("subreddits", []),
            }
            for item in aggregated
        }
        self._cache_date = asof

        qualifying_tickers = list(self._sentiment_cache.keys())
        ticker_list = ", ".join(qualifying_tickers[:10])
        if len(qualifying_tickers) > 10:
            ticker_list += f"... (+{len(qualifying_tickers) - 10} more)"

        logger.info(
            f"✅ Found {len(self._sentiment_cache)} qualifying candidates: {ticker_list}",
            tickers=len(self._sentiment_cache),
            date=str(asof),
        )

    def filters(self, ticker_data: dict[str, Any]) -> bool:
        """Filter tickers based on Reddit sentiment.

        NOTE: This method is not used when provides_own_universe=True.
        The scanner calls get_universe() instead to get only Reddit-mentioned tickers.

        Args:
            ticker_data: Dictionary with ticker info (must have 'symbol' and 'asof')

        Returns:
            True if ticker should be processed (has positive sentiment on Reddit)
        """
        symbol = ticker_data.get("symbol", ticker_data.get("ticker", ""))
        asof = ticker_data.get("asof")

        # Refresh sentiment data if needed
        if asof and isinstance(asof, date):
            self._refresh_sentiment_data(asof)

        # Check if ticker is in Reddit sentiment cache
        return symbol in self._sentiment_cache

    def get_universe(self, asof: date) -> list[str]:
        """Get custom universe of tickers mentioned on Reddit.

        This method is called by the scanner when provides_own_universe=True.
        It replaces the default S&P 500 universe with tickers discovered from Reddit.

        Args:
            asof: Date to fetch data for

        Returns:
            List of ticker symbols mentioned on Reddit with positive sentiment
        """
        # Refresh sentiment data (fetches Reddit posts if cache stale)
        self._refresh_sentiment_data(asof)

        # Return only tickers in the cache (already filtered by sentiment)
        return list(self._sentiment_cache.keys())

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """Extract sentiment features including detailed LLM rationale and cross-subreddit data.

        Args:
            ticker_data: Dictionary with ticker info

        Returns:
            Dictionary with sentiment, mentions, detailed LLM reasoning, and subreddit coverage
        """
        symbol = ticker_data.get("symbol", ticker_data.get("ticker", ""))
        rationale = self._rationale_cache.get(symbol, {})

        return {
            "sentiment": self._sentiment_cache.get(symbol, 0.0),
            "mentions": self._mentions_cache.get(symbol, 0),
            # Include detailed LLM rationale for transparency
            "llm_reasoning": rationale.get("all_reasoning", []),
            "catalysts": rationale.get("catalysts", []),
            "risk_factors": rationale.get("risk_factors", []),
            "sentiment_details": rationale.get("sentiment_details", []),
            # Include cross-subreddit data
            "subreddit_count": rationale.get("subreddit_count", 1),
            "subreddits": rationale.get("subreddits", []),
        }

    def score(self, features: dict[str, Any]) -> float:
        """Score candidate based on sentiment.

        Args:
            features: Dictionary with features

        Returns:
            Normalized sentiment score (0-1)
        """
        sentiment = features.get("sentiment", 0.0)
        return float(min(max(sentiment, 0.0), 1.0))

    def label(self, entry_data: dict[str, Any], outcome_data: dict[str, Any]) -> bool:
        """Label outcome (placeholder for Phase 5).

        Args:
            entry_data: Entry point data
            outcome_data: Outcome data

        Returns:
            False (not implemented yet)
        """
        return False


# Helper to get candidates for scan


def get_candidates(
    date: str | None = None,
    top_n: int = 20,
    sentiment_threshold: float = 0.5,
    subreddit: str = "wallstreetbets",
    post_limit: int = 100,
) -> dict[str, Any]:
    """Get top candidates from Reddit sentiment aggregation.

    Args:
        date: Date string (unused, for future historical support)
        top_n: Number of top candidates to return
        sentiment_threshold: Minimum weighted score to include
        subreddit: Subreddit to fetch from
        post_limit: Number of posts to fetch

    Returns:
        Dict with candidates list, strategy metadata
    """
    # Initialize adapters
    reddit = RedditAdapter(cache_enabled=True)
    sentiment_analyzer = SentimentAnalyzer(cache_enabled=True)

    # Fetch posts
    posts = reddit.fetch_hot_posts(subreddit=subreddit, limit=post_limit)

    # Analyze sentiment for all tickers
    sentiment_results = sentiment_analyzer.analyze_batch(posts)

    # Aggregate and filter
    aggregated = aggregate_ticker_sentiments(
        sentiment_results,
        min_mentions=2,
        min_confidence=0.6,
        min_weighted_score=sentiment_threshold,
    )

    # Take top N
    top_tickers = aggregated[:top_n]

    # Apply strategy scoring
    config = StrategyConfig(
        name="reddit",
        version="1.0.0",
        description="Reddit sentiment strategy",
        enabled=True,
        parameters={
            "sentiment_threshold": sentiment_threshold,
            "top_n": top_n,
            "subreddit": subreddit,
            "post_limit": post_limit,
        },
    )
    strategy = RedditSentimentStrategy(config=config)
    candidates = []

    for ticker_data in top_tickers:
        # Convert aggregated data to format expected by strategy
        strategy_input = {
            "ticker": ticker_data["ticker"],
            "sentiment": ticker_data["weighted_score"],
            "mentions": ticker_data["mentions"],
        }

        if strategy.filters(strategy_input):
            feats = strategy.features(strategy_input)
            score = strategy.score(feats)
            candidates.append(
                {
                    "ticker": ticker_data["ticker"],
                    "score": score,
                    "features": feats,
                    "aggregated_data": ticker_data,
                }
            )

    return {
        "candidates": candidates,
        "strategy": strategy.name,
        "version": strategy.version,
        "total_tickers": len(sentiment_results),
        "total_aggregated": len(aggregated),
        "posts_analyzed": len(posts),
    }
