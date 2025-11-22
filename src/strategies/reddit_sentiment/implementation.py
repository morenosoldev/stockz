import time
from datetime import date
from typing import Any

from src.analysis.technical_analyzer import TechnicalAnalyzer
from src.datasources.aggregation import aggregate_ticker_sentiments
from src.datasources.company import CompanyAdapter
from src.datasources.reddit import RedditAdapter
from src.datasources.sentiment import SentimentAnalyzer
from src.datasources.technical import TechnicalDataAdapter
from src.ops.logging import get_logger
from src.research import (
    analyze_narrative,
    deduplicate_claims,
    extract_claims_batched,
    fact_check_claims,
)

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

        # Research pipeline configuration
        self.research_enabled = params.get("research_enabled", False)
        self.research_comments_limit = params.get("research_comments_limit", 20)
        self.research_batch_size = params.get("research_batch_size", 10)
        self.research_max_claims_to_verify = params.get("research_max_claims_to_verify", 10)

        # Technical analysis configuration
        self.technical_analysis_enabled = params.get("technical_analysis_enabled", False)
        self.technical_lookback_days = params.get("technical_lookback_days", 90)
        self.technical_cache_ttl = params.get("technical_cache_ttl", 3600)
        self.technical_bullish_boost_max = params.get("technical_bullish_boost_max", 0.15)
        self.technical_bearish_penalty_max = params.get("technical_bearish_penalty_max", 0.20)
        self.technical_high_risk_penalty = params.get("technical_high_risk_penalty", 0.10)
        self.technical_min_signal_strength = params.get("technical_min_signal_strength", 0.5)

        # Initialize adapters (lazy load to avoid API calls during registration)
        self._reddit_adapter: RedditAdapter | None = None
        self._sentiment_analyzer: SentimentAnalyzer | None = None
        self._company_adapter: CompanyAdapter | None = None
        self._technical_adapter: TechnicalDataAdapter | None = None
        self._technical_analyzer: TechnicalAnalyzer | None = None
        self._sentiment_cache: dict[str, float] = {}
        self._mentions_cache: dict[str, int] = {}
        self._rationale_cache: dict[str, dict[str, Any]] = {}  # Store detailed LLM rationale
        self._technical_cache: dict[str, dict[str, Any]] = {}  # Store technical analysis
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

    @property
    def company_adapter(self) -> CompanyAdapter:
        """Lazy-load company adapter."""
        if self._company_adapter is None:
            self._company_adapter = CompanyAdapter()
        return self._company_adapter

    @property
    def technical_adapter(self) -> TechnicalDataAdapter:
        """Lazy-load technical data adapter."""
        if self._technical_adapter is None:
            self._technical_adapter = TechnicalDataAdapter(
                cache_ttl_seconds=self.technical_cache_ttl
            )
        return self._technical_adapter

    @property
    def technical_analyzer(self) -> TechnicalAnalyzer:
        """Lazy-load technical analyzer."""
        if self._technical_analyzer is None:
            self._technical_analyzer = TechnicalAnalyzer()
        return self._technical_analyzer

    def _refresh_sentiment_data(self, asof: date, run_id: str | None = None) -> None:
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

        from src.scanner.engine import is_interrupted

        # Cooperative interrupt before starting expensive network calls
        if run_id and is_interrupted(run_id):
            logger.info(
                "⏹️ Scan interrupted before subreddit fetch phase",
                run_id=run_id,
            )
            return

        for subreddit in self.subreddits:
            if run_id and is_interrupted(run_id):
                logger.info(
                    "⏹️ Scan interrupted during subreddit iteration",
                    run_id=run_id,
                    subreddit=subreddit,
                )
                break
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

        # Analyze sentiment (including comments) unless interrupted
        if run_id and is_interrupted(run_id):
            logger.info(
                "⏹️ Scan interrupted before sentiment analysis phase",
                run_id=run_id,
                posts=len(all_posts),
            )
            sentiment_results = {}
        else:
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

        # Run deep research if enabled
        if self.research_enabled:
            if run_id and is_interrupted(run_id):
                logger.info(
                    "⏹️ Scan interrupted before deep research pipeline",
                    run_id=run_id,
                )
            else:
                logger.info(
                    "🔬 Starting deep research pipeline for top candidates...",
                    candidates_count=len(aggregated),
                )
                self._run_deep_research(aggregated, all_posts, run_id=run_id)

        # Run technical analysis if enabled
        if self.technical_analysis_enabled:
            if run_id and is_interrupted(run_id):
                logger.info(
                    "⏹️ Scan interrupted before technical analysis pipeline",
                    run_id=run_id,
                )
            else:
                logger.info(
                    "📊 Starting technical analysis for top candidates...",
                    candidates_count=len(aggregated),
                )
                self._run_technical_analysis(aggregated, asof, run_id=run_id)

        qualifying_tickers = list(self._sentiment_cache.keys())
        ticker_list = ", ".join(qualifying_tickers[:10])
        if len(qualifying_tickers) > 10:
            ticker_list += f"... (+{len(qualifying_tickers) - 10} more)"

        logger.info(
            f"✅ Found {len(self._sentiment_cache)} qualifying candidates: {ticker_list}",
            tickers=len(self._sentiment_cache),
            date=str(asof),
        )

    def _run_deep_research(
        self,
        candidates: list[dict[str, Any]],
        all_posts: list[dict[str, Any]],
        run_id: str | None = None,
    ) -> None:
        """Run deep research pipeline for candidates.

        Extracts claims from Reddit comments, fact-checks them with web research,
        gathers company intelligence, and enriches rationale cache with research data.

        Args:
            candidates: List of candidate dicts with ticker, weighted_score, etc.
            all_posts: All Reddit posts with comments
        """
        from src.scanner.engine import is_interrupted

        for candidate in candidates:
            if run_id and is_interrupted(run_id):
                logger.info(
                    "⏹️ Scan interrupted during deep research loop",
                    run_id=run_id,
                    remaining=len(candidates),
                )
                break
            ticker = candidate["ticker"]
            logger.info(f"  🔎 Researching {ticker}...", ticker=ticker)

            try:
                # 1. Collect comments mentioning this ticker
                ticker_comments = []
                for post in all_posts:
                    if ticker in post.get("tickers", []):
                        # Get post comments up to limit
                        comments = post.get("comments", [])[: self.research_comments_limit]
                        # Filter comments that mention the ticker
                        relevant_comments = [
                            c for c in comments if ticker.upper() in c.get("body", "").upper()
                        ]
                        ticker_comments.extend(relevant_comments)

                # Limit to top N comments by score
                ticker_comments = sorted(
                    ticker_comments, key=lambda c: c.get("score", 0), reverse=True
                )[: self.research_comments_limit]

                if not ticker_comments:
                    logger.info(
                        f"  ⏭️ No comments found for {ticker}, skipping research", ticker=ticker
                    )
                    continue

                logger.info(
                    f"  📝 Found {len(ticker_comments)} relevant comments for {ticker}",
                    ticker=ticker,
                    comments_count=len(ticker_comments),
                )

                # 2. Extract claims from comments
                claims = extract_claims_batched(
                    ticker_comments,
                    ticker,
                    batch_size=self.research_batch_size,
                )

                if not claims:
                    logger.info(f"  ⏭️ No claims extracted for {ticker}", ticker=ticker)
                    continue

                # 3. Deduplicate claims
                deduplicated_claims = deduplicate_claims(claims)

                logger.info(
                    f"  📊 Extracted {len(claims)} claims ({len(deduplicated_claims)} unique) for {ticker}",
                    ticker=ticker,
                    raw_claims=len(claims),
                    unique_claims=len(deduplicated_claims),
                )

                # 4. Fact-check top claims
                fact_check_results = fact_check_claims(
                    deduplicated_claims,
                    max_claims=self.research_max_claims_to_verify,
                )

                logger.info(
                    f"  ✅ Fact-checked {len(fact_check_results)} claims for {ticker}",
                    ticker=ticker,
                    verified=sum(1 for r in fact_check_results if r.verified),
                    debunked=sum(1 for r in fact_check_results if not r.verified),
                )

                # 5. Analyze narrative consensus
                narrative = analyze_narrative(deduplicated_claims, ticker_comments, ticker)

                logger.info(
                    f"  💬 Narrative: {narrative.primary_theme[:60]}...",
                    ticker=ticker,
                    consensus_strength=narrative.consensus_strength,
                )

                # 6. Gather company intelligence
                company_data = self.company_adapter.get_company_data(ticker)

                logger.info(
                    f"  🏢 Company data: {company_data.company_name}",
                    ticker=ticker,
                    revenue_growth=company_data.revenue_growth_yoy,
                    confidence=company_data.confidence,
                )

                # 7. Enrich rationale cache with research data
                if ticker not in self._rationale_cache:
                    self._rationale_cache[ticker] = {}

                self._rationale_cache[ticker]["research"] = {
                    "claims": {
                        "total": len(claims),
                        "unique": len(deduplicated_claims),
                        "top_claims": [
                            {
                                "text": c.text,
                                "category": c.category,
                                "confidence": c.confidence,
                            }
                            for c in deduplicated_claims[:5]
                        ],
                    },
                    "fact_checks": {
                        "verified": [
                            {
                                "claim": r.claim.text,
                                "confidence": r.confidence,
                                "sources": r.sources[:3],  # Top 3 sources
                            }
                            for r in fact_check_results
                            if r.verified
                        ],
                        "debunked": [
                            {
                                "claim": r.claim.text,
                                "evidence": r.evidence[:100],  # Summary
                            }
                            for r in fact_check_results
                            if not r.verified
                        ],
                    },
                    "narrative": {
                        "primary_theme": narrative.primary_theme,
                        "secondary_themes": narrative.secondary_themes,
                        "contradicting_views": narrative.contradicting_views,
                        "consensus_strength": narrative.consensus_strength,
                    },
                    "company": {
                        "name": company_data.company_name,
                        "sector": company_data.sector,
                        "market_cap": company_data.market_cap,
                        "revenue_growth_yoy": company_data.revenue_growth_yoy,
                        "recent_news": company_data.recent_news[:3],  # Top 3 news
                        "catalyst_events": company_data.catalyst_events,
                        "analyst_rating": company_data.analyst_rating,
                        "confidence": company_data.confidence,
                    },
                }

                logger.info(f"  ✨ Research complete for {ticker}", ticker=ticker)

            except Exception as e:
                logger.error(
                    f"  ❌ Research failed for {ticker}: {e}",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True,
                )
                # Continue with other tickers even if one fails
                continue

    def _run_technical_analysis(
        self,
        candidates: list[dict[str, Any]],
        asof: date,
        run_id: str | None = None,
    ) -> None:
        """Run technical analysis for candidates.

        Fetches OHLCV data, calculates technical indicators, and uses GPT-4
        to analyze and provide trading signals.

        Args:
            candidates: List of candidate dicts with ticker, weighted_score, etc.
            asof: Analysis date
        """
        from src.scanner.engine import is_interrupted

        for candidate in candidates:
            if run_id and is_interrupted(run_id):
                logger.info(
                    "⏹️ Scan interrupted during technical analysis loop",
                    run_id=run_id,
                    remaining=len(candidates),
                )
                break
            ticker = candidate["ticker"]
            logger.info(f"  📈 Analyzing {ticker} technical data...", ticker=ticker)

            try:
                # 1. Fetch technical data and calculate indicators
                technical_data = self.technical_adapter.get_technical_data(
                    ticker=ticker,
                    lookback_days=self.technical_lookback_days,
                    as_of_date=asof,
                )

                logger.info(
                    f"  📊 Indicators calculated for {ticker}",
                    ticker=ticker,
                    rsi=technical_data.rsi,
                    macd_histogram=technical_data.macd_histogram,
                    bb_width=technical_data.bb_width,
                    adx=technical_data.adx,
                )

                # 2. Analyze with GPT-4
                analysis = self.technical_analyzer.analyze_technical_data(technical_data)

                logger.info(
                    f"  ✅ Technical analysis: {analysis.overall_signal} "
                    f"(strength: {analysis.signal_strength:.2f}, confidence: {analysis.confidence:.2f})",
                    ticker=ticker,
                    signal=analysis.overall_signal,
                    strength=analysis.signal_strength,
                    confidence=analysis.confidence,
                    risk=analysis.risk_assessment,
                )

                # 3. Store in cache for scoring
                self._technical_cache[ticker] = {
                    "data": technical_data,
                    "analysis": analysis,
                }

                # 4. Enrich rationale cache
                if ticker not in self._rationale_cache:
                    self._rationale_cache[ticker] = {}

                self._rationale_cache[ticker]["technical_analysis"] = {
                    "signal": analysis.overall_signal,
                    "strength": analysis.signal_strength,
                    "key_signals": analysis.key_signals,
                    "price_targets": analysis.price_targets,
                    "risk": analysis.risk_assessment,
                    "summary": analysis.summary,
                    "confidence": analysis.confidence,
                    "indicators": {
                        "rsi": technical_data.rsi,
                        "macd_histogram": technical_data.macd_histogram,
                        "bb_width": technical_data.bb_width,
                        "adx": technical_data.adx,
                        "volume_ratio": technical_data.volume_ratio,
                    },
                }

                logger.info(f"  ✨ Technical analysis complete for {ticker}", ticker=ticker)

                # Add 5-second delay to avoid rate limiting
                logger.info("  ⏱️ Waiting 5 seconds before next analysis (rate limit protection)...")
                time.sleep(5)

            except ValueError as e:
                # Expected errors (invalid ticker, no data)
                logger.warning(
                    f"  ⏭️ Skipping {ticker}: {e}",
                    ticker=ticker,
                    error=str(e),
                )
                continue
            except Exception as e:
                # Unexpected errors - log but don't fail entire scan
                logger.error(
                    f"  ❌ Technical analysis failed for {ticker}: {e}",
                    ticker=ticker,
                    error=str(e),
                    exc_info=True,
                )
                continue

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

    def get_universe(self, asof: date, run_id: str | None = None) -> list[str]:
        """Get custom universe of tickers mentioned on Reddit.

        This method is called by the scanner when provides_own_universe=True.
        It replaces the default S&P 500 universe with tickers discovered from Reddit.

        Args:
            asof: Date to fetch data for

        Returns:
            List of ticker symbols mentioned on Reddit with positive sentiment
        """
        # Refresh sentiment data (fetches Reddit posts if cache stale)
        self._refresh_sentiment_data(asof, run_id=run_id)

        # Return only tickers in the cache (already filtered by sentiment)
        return list(self._sentiment_cache.keys())

    def features(self, ticker_data: dict[str, Any]) -> dict[str, Any]:
        """Extract sentiment features including detailed LLM rationale, cross-subreddit data,
        and technical analysis.

        Args:
            ticker_data: Dictionary with ticker info

        Returns:
            Dictionary with sentiment, mentions, detailed LLM reasoning, subreddit coverage,
            research data, and technical analysis
        """
        symbol = ticker_data.get("symbol", ticker_data.get("ticker", ""))
        rationale = self._rationale_cache.get(symbol, {})

        features_dict = {
            "ticker": symbol,  # Include ticker for score adjustments
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

        # Include research data if available
        if "research" in rationale:
            features_dict["research"] = rationale["research"]

        # Include technical analysis if available
        if self.technical_analysis_enabled and symbol in self._technical_cache:
            technical_data = self._technical_cache[symbol]
            if technical_data and technical_data.get("analysis"):
                analysis = technical_data["analysis"]
                data = technical_data["data"]

                features_dict["technical_analysis"] = {
                    # Overall signal
                    "signal": analysis.overall_signal,
                    "signal_strength": analysis.signal_strength,
                    "confidence": analysis.confidence,
                    "risk_assessment": analysis.risk_assessment,
                    # Key findings
                    "key_signals": analysis.key_signals,
                    "summary": analysis.summary,
                    "support_level": analysis.support_level,
                    "resistance_level": analysis.resistance_level,
                    "price_targets": analysis.price_targets,
                    # Technical indicators (for frontend charts)
                    "indicators": {
                        # Trend
                        "sma_20": data.sma_20,
                        "sma_50": data.sma_50,
                        "sma_200": data.sma_200,
                        "ema_20": data.ema_20,
                        "ema_50": data.ema_50,
                        # Momentum
                        "rsi": data.rsi,
                        "macd": data.macd,
                        "macd_signal": data.macd_signal,
                        "macd_histogram": data.macd_histogram,
                        "stochastic_k": data.stochastic_k,
                        "stochastic_d": data.stochastic_d,
                        # Volatility
                        "bb_upper": data.bb_upper,
                        "bb_middle": data.bb_middle,
                        "bb_lower": data.bb_lower,
                        "bb_width": data.bb_width,
                        "atr": data.atr,
                        # Trend Strength
                        "adx": data.adx,
                        # Volume
                        "current_volume": data.current_volume,
                        "avg_volume_20d": data.avg_volume_20d,
                        "volume_ratio": data.volume_ratio,
                    },
                    # Price context
                    "current_price": data.current_price,
                    "support": data.support,
                    "resistance": data.resistance,
                }

        return features_dict

    def score(self, features: dict[str, Any]) -> float:
        """Score candidate based on sentiment with research-based adjustments.

        Base score is sentiment (0-1), then adjusted by:
        - Verified claims: +0.05 per claim (max +0.15)
        - Debunked claims: -0.10 per claim (max -0.30)
        - Strong fundamentals: +0.10 if revenue_growth > 15%
        - Consensus bonus: +0.05 if consensus_strength >= 0.8
        - Multi-subreddit boost: Already applied in _refresh_sentiment_data

        Args:
            features: Dictionary with sentiment and research features

        Returns:
            Adjusted score (0-1)
        """
        # Start with base sentiment score
        base_score = features.get("sentiment", 0.0)
        score = float(base_score)

        # Research-based adjustments (only if research was run)
        research = features.get("research")
        if research:
            ticker = features.get("ticker", "UNKNOWN")

            # Verified claims bonus (+0.05 each, max +0.15)
            verified_claims = research.get("fact_checks", {}).get("verified", [])
            verified_bonus = min(len(verified_claims) * 0.05, 0.15)
            if verified_bonus > 0:
                score += verified_bonus
                logger.info(
                    f"  ✅ {ticker}: +{verified_bonus:.2f} bonus for {len(verified_claims)} verified claims",
                    ticker=ticker,
                    verified_count=len(verified_claims),
                    bonus=verified_bonus,
                )

            # Debunked claims penalty (-0.10 each, max -0.30)
            debunked_claims = research.get("fact_checks", {}).get("debunked", [])
            debunked_penalty = min(len(debunked_claims) * 0.10, 0.30)
            if debunked_penalty > 0:
                score -= debunked_penalty
                logger.info(
                    f"  ❌ {ticker}: -{debunked_penalty:.2f} penalty for {len(debunked_claims)} debunked claims",
                    ticker=ticker,
                    debunked_count=len(debunked_claims),
                    penalty=debunked_penalty,
                )

            # Strong fundamentals bonus (+0.10 if revenue_growth > 15%)
            company = research.get("company", {})
            revenue_growth = company.get("revenue_growth_yoy")
            if revenue_growth and revenue_growth > 15.0:
                score += 0.10
                logger.info(
                    f"  📈 {ticker}: +0.10 bonus for strong revenue growth ({revenue_growth:.1f}%)",
                    ticker=ticker,
                    revenue_growth=revenue_growth,
                )

            # Narrative consensus bonus (+0.05 if consensus_strength >= 0.8)
            narrative = research.get("narrative", {})
            consensus_strength = narrative.get("consensus_strength", 0.0)
            if consensus_strength >= 0.8:
                score += 0.05
                logger.info(
                    f"  💪 {ticker}: +0.05 bonus for strong consensus ({consensus_strength:.2f})",
                    ticker=ticker,
                    consensus=consensus_strength,
                )

        # Technical analysis adjustments (only if enabled and data available)
        if self.technical_analysis_enabled:
            ticker = features.get("ticker", "UNKNOWN")
            technical_data = self._technical_cache.get(ticker)

            if technical_data and technical_data.get("analysis"):
                analysis = technical_data["analysis"]

                # Only apply adjustments if signal strength is strong enough
                if analysis.signal_strength >= self.technical_min_signal_strength:
                    # Bullish signal boost (+strength * 0.15 max)
                    if analysis.overall_signal == "BULLISH":
                        boost = analysis.signal_strength * self.technical_bullish_boost_max
                        score += boost
                        logger.info(
                            f"  📈 {ticker}: +{boost:.2f} technical bullish boost (strength: {analysis.signal_strength:.2f})",
                            ticker=ticker,
                            boost=boost,
                            signal=analysis.overall_signal,
                            strength=analysis.signal_strength,
                        )

                    # Bearish signal penalty (-strength * 0.20 max)
                    elif analysis.overall_signal == "BEARISH":
                        penalty = analysis.signal_strength * self.technical_bearish_penalty_max
                        score -= penalty
                        logger.info(
                            f"  📉 {ticker}: -{penalty:.2f} technical bearish penalty (strength: {analysis.signal_strength:.2f})",
                            ticker=ticker,
                            penalty=penalty,
                            signal=analysis.overall_signal,
                            strength=analysis.signal_strength,
                        )

                    # High risk penalty (-0.10)
                    if analysis.risk_assessment == "HIGH":
                        score -= self.technical_high_risk_penalty
                        logger.info(
                            f"  ⚠️  {ticker}: -{self.technical_high_risk_penalty:.2f} high risk penalty",
                            ticker=ticker,
                            risk=analysis.risk_assessment,
                            penalty=self.technical_high_risk_penalty,
                        )

        # Clamp score to [0, 1]
        final_score = float(min(max(score, 0.0), 1.0))

        # Log if score was adjusted
        if research and abs(final_score - base_score) > 0.001:
            ticker = features.get("ticker", "UNKNOWN")
            logger.info(
                f"  🎯 {ticker}: Score adjusted {base_score:.3f} → {final_score:.3f} (Δ {final_score - base_score:+.3f})",
                ticker=ticker,
                base_score=base_score,
                final_score=final_score,
                adjustment=final_score - base_score,
            )

        return final_score

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
