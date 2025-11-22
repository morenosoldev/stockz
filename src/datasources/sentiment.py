"""LLM-based sentiment analyzer for Reddit posts.

This module uses OpenAI's structured outputs to analyze sentiment of Reddit posts
mentioning stock tickers. It provides structured sentiment scores with
confidence levels and reasoning.

All sentiment analysis is cached to minimize API costs and latency.
"""

import json
from datetime import UTC, datetime
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from src.datasources.attribution import Attribution
from src.datasources.base import DataAdapterError, DataSource
from src.datasources.cache import CachedDataAdapter
from src.ops.logging import get_logger

logger = get_logger(__name__)


def calculate_weighted_score(
    fundamentals: float,
    potential: float,
    conviction: float,
    sentiment: str,
) -> float:
    """Calculate final weighted score from three dimensions.

    Formula:
    - Base = (fundamentals × 0.3) + (potential × 0.4) + (conviction × 0.3)
    - Scale to -1.0 to +1.0 based on sentiment direction

    Args:
        fundamentals: Current business health (0-1)
        potential: Future opportunity (0-1)
        conviction: Research quality (0-1)
        sentiment: Direction ("bullish", "bearish", "neutral")

    Returns:
        Final score -1.0 to +1.0

    Examples:
        - fundamentals=0.3, potential=0.9, conviction=0.7, bullish
          → base = 0.09 + 0.36 + 0.21 = 0.66
          → final = 0.66 (bullish, so positive)

        - fundamentals=0.8, potential=0.9, conviction=0.9, bullish
          → base = 0.24 + 0.36 + 0.27 = 0.87
          → final = 0.87 (strongly bullish)

        - fundamentals=0.2, potential=0.3, conviction=0.4, bearish
          → base = 0.06 + 0.12 + 0.12 = 0.30
          → final = -0.30 (bearish)
    """
    # Weighted combination emphasizing potential (40%) over fundamentals (30%)
    base_score = (fundamentals * 0.3) + (potential * 0.4) + (conviction * 0.3)

    # Map to -1.0 to +1.0 based on sentiment direction
    if sentiment == "bullish":
        return base_score  # 0 to 1.0
    elif sentiment == "bearish":
        return -base_score  # 0 to -1.0
    else:  # neutral
        return 0.0


class SentimentScore(BaseModel):
    """Structured sentiment analysis output with balanced fundamentals & potential scoring.

    Attributes:
        ticker: Stock ticker symbol
        sentiment: Overall sentiment (bullish, bearish, neutral)
        confidence: Confidence score 0.0-1.0 (how certain the model is)
        score: Numeric score -1.0 to 1.0 (-1=bearish, 0=neutral, 1=bullish)

        # NEW: Three-dimensional scoring
        fundamentals_score: Current business health 0.0-1.0
        potential_score: Future opportunity/catalysts 0.0-1.0
        conviction_score: Quality of research/evidence 0.0-1.0

        reasoning: Brief explanation of the sentiment
        catalysts: Key factors mentioned (e.g., "earnings beat", "FDA approval")
        risk_factors: Mentioned risks or concerns
        growth_drivers: Why this could 10x (new products, market expansion, etc.)
    """

    ticker: str = Field(description="Stock ticker symbol")
    sentiment: str = Field(description="Overall sentiment: bullish, bearish, or neutral")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)
    score: float = Field(
        description="Numeric score -1.0 (bearish) to 1.0 (bullish)", ge=-1.0, le=1.0
    )

    # NEW: Three-dimensional scoring (fundamentals 30%, potential 40%, conviction 30%)
    fundamentals_score: float = Field(
        description="Current business health: 0=bankrupt, 0.5=break-even, 1.0=highly profitable",
        ge=0.0,
        le=1.0,
    )
    potential_score: float = Field(
        description="Future opportunity: 0=no catalysts, 0.5=moderate potential, 1.0=revolutionary",
        ge=0.0,
        le=1.0,
    )
    conviction_score: float = Field(
        description="Research quality: 0=pure speculation, 0.5=reasonable thesis, 1.0=deep research",
        ge=0.0,
        le=1.0,
    )

    reasoning: str = Field(description="Brief explanation of sentiment")
    catalysts: list[str] = Field(default_factory=list, description="Positive catalysts mentioned")
    risk_factors: list[str] = Field(default_factory=list, description="Risks or concerns mentioned")
    growth_drivers: list[str] = Field(
        default_factory=list,
        description="Why this could 10x (breakthrough products, market expansion, etc.)",
    )


class SentimentAnalyzer(CachedDataAdapter):
    """LLM-based sentiment analyzer for stock-related content.

    Uses OpenAI GPT-4o-mini with structured outputs to analyze sentiment of Reddit posts,
    comments, and other text content mentioning stock tickers.

    Provides structured output with sentiment, confidence, and reasoning.
    All results are cached to minimize API costs.

    Attributes:
        client: OpenAI client instance
        model: OpenAI model name
        temperature: LLM temperature (0 = deterministic)

    Example:
        >>> analyzer = SentimentAnalyzer()
        >>> sentiment = analyzer.analyze_post(
        ...     ticker="NVDA",
        ...     title="NVDA crushes earnings, stock up 10%",
        ...     body="Amazing quarter, AI demand is insane..."
        ... )
        >>> sentiment.sentiment
        'bullish'
        >>> sentiment.confidence
        0.92
    """

    source = DataSource.INTERNAL

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        cache_enabled: bool = True,
        cache_ttl: int = 86400,  # 24 hours
    ) -> None:
        """Initialize sentiment analyzer.

        Args:
            model: OpenAI model name (default: gpt-4o-mini for cost efficiency)
            temperature: LLM temperature 0.0-1.0 (0=deterministic, 1=creative)
            cache_enabled: Whether to cache results (recommended for cost)
            cache_ttl: Cache TTL in seconds (default: 24 hours)
        """
        super().__init__(cache_enabled=cache_enabled, cache_ttl=cache_ttl)

        self.model = model
        self.temperature = temperature

        # OpenAI client uses OPENAI_API_KEY env var by default
        self.client = OpenAI()  # Will read from OPENAI_API_KEY env var

        logger.info(
            "SentimentAnalyzer initialized",
            extra={"model": self.model, "temperature": self.temperature},
        )

    def analyze_post(
        self,
        ticker: str,
        title: str,
        body: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SentimentScore:
        """Analyze sentiment of a Reddit post.

        Args:
            ticker: Stock ticker symbol
            title: Post title
            body: Post body/selftext (optional)
            metadata: Optional metadata (score, comments, etc.)

        Returns:
            SentimentScore with structured analysis

        Raises:
            DataAdapterError: If LLM call fails
        """
        # Create cache key
        cache_key = {
            "ticker": ticker.upper(),
            "title": title[:200],  # Limit length for cache key
            "body": body[:500] if body else "",
            "model": self.model,
        }

        # Try cache first
        if self.cache_enabled:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                try:
                    # Validate cached data has all required fields
                    sentiment = SentimentScore(**cached)
                    logger.debug(
                        "Sentiment fetched from cache",
                        extra={"ticker": ticker},
                    )
                    return sentiment
                except Exception as e:
                    # Cache data is stale/invalid (missing new fields), ignore it
                    logger.debug(
                        "Cached sentiment data is stale, will re-analyze",
                        extra={"ticker": ticker, "error": str(e)},
                    )

        # Call OpenAI API with structured outputs
        try:
            logger.debug(
                "Calling OpenAI for sentiment analysis",
                extra={"ticker": ticker, "model": self.model},
            )

            # Create the balanced growth-focused prompt
            prompt = f"""You are a growth-focused investment analyst who evaluates stocks based on BOTH current fundamentals AND future potential.

Your philosophy:
- A struggling company with a revolutionary product is MORE exciting than a stable company with no growth
- Past performance matters, but future catalysts matter MORE
- Be open-minded to contrarian opportunities
- High risk + high reward = bullish if the upside is 10x+

Analyze this Reddit post/comment about {ticker.upper()}:

Title: {title}

Body: {body or "No body text"}

Evaluate in 3 dimensions:

1. FUNDAMENTALS (Current State - 30% weight):
   - Is the business profitable or on path to profitability?
   - Does it have revenue? Growing or declining?
   - Is it well-managed? Any red flags (debt, lawsuits)?
   - Score 0-1: 0=bankrupt, 0.5=break-even, 1.0=highly profitable

2. POTENTIAL (Future Catalysts - 40% weight):
   - What could make this 10x in 2-5 years?
   - Product launches, FDA approvals, market expansion?
   - Does the author cite specific upcoming events?
   - Is this a paradigm shift (AI, biotech, clean energy)?
   - Score 0-1: 0=no catalysts, 0.5=moderate potential, 1.0=revolutionary

3. CONVICTION (Community Belief - 30% weight):
   - How confident is the author?
   - Do they provide evidence or just hype?
   - Is this based on research or memes?
   - Score 0-1: 0=pure speculation, 0.5=reasonable thesis, 1.0=deep research

Return your analysis with:
- ticker: Stock symbol
- sentiment: "bullish", "bearish", or "neutral"
- confidence: Your confidence in this analysis (0-1)
- score: Overall score -1 to +1

- fundamentals_score: Current business health (0-1)
- potential_score: Future opportunity (0-1)
- conviction_score: Author's research quality (0-1)

- reasoning: Brief explanation of your assessment
- catalysts: List of positive catalysts mentioned
- risk_factors: List of risks or concerns mentioned
- growth_drivers: Why this could 10x (specific products, markets, advantages)

IMPORTANT:
- Don't dismiss a stock just because it's unprofitable today
- DO dismiss if there are NO growth drivers (stagnant business)
- Weight POTENTIAL higher than FUNDAMENTALS for high-growth plays
- Be skeptical of pure hype, but open to contrarian opportunities
- If fundamentals are weak BUT potential is high, score can still be 0.7+
- Focus on WHAT COULD BE, not just what IS"""

            # Call API with structured output
            completion = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a growth-focused investment analyst (mix of Peter Thiel + Cathie Wood). You value future potential as much as current fundamentals.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=SentimentScore,
                temperature=self.temperature,
            )

            result: SentimentScore | None = completion.choices[0].message.parsed

            # Handle case where parsing failed
            if result is None:
                raise DataAdapterError(
                    f"LLM failed to return structured output for {ticker}",
                    source=self.source,
                )

            # Build attribution
            self._last_attribution = self._build_attribution(
                metadata={
                    "model": self.model,
                    "temperature": self.temperature,
                    "ticker": ticker,
                    "title_length": len(title),
                    "body_length": len(body) if body else 0,
                }
            )

            # Cache result
            if self.cache_enabled:
                self._save_to_cache(cache_key, result.model_dump())

            logger.info(
                "Sentiment analysis completed",
                extra={
                    "ticker": ticker,
                    "sentiment": result.sentiment,
                    "confidence": result.confidence,
                    "score": result.score,
                    "fundamentals": result.fundamentals_score,
                    "potential": result.potential_score,
                    "conviction": result.conviction_score,
                },
            )

            return result

        except Exception as e:
            logger.error(
                "Sentiment analysis failed",
                extra={"ticker": ticker, "error": str(e)},
                exc_info=True,
            )
            raise DataAdapterError(
                f"Failed to analyze sentiment for {ticker}: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def analyze_comments_batch(
        self,
        ticker: str,
        post_title: str,
        comments: list[dict[str, Any]],
        batch_size: int = 10,
    ) -> list[SentimentScore]:
        """Analyze sentiment for multiple comments in a single batched LLM call.

        This is ~10x more efficient than calling analyze_post() in a loop for comments.

        Args:
            ticker: Stock ticker symbol
            post_title: Original post title (for context)
            comments: List of comment dicts with 'body', 'score', 'id' keys
            batch_size: Number of comments per LLM call (default: 10)

        Returns:
            List of SentimentScore objects (one per comment)

        Example:
            >>> comments = [{"body": "Great company!", "score": 50, "id": "abc123"}, ...]
            >>> sentiments = analyzer.analyze_comments_batch("NVDA", "NVDA earnings", comments)
        """
        results: list[SentimentScore] = []

        try:
            # Process comments in batches
            for i in range(0, len(comments), batch_size):
                batch = comments[i : i + batch_size]

                # Build batch input as JSON array
                comments_data = []
                for idx, comment in enumerate(batch):
                    comments_data.append(
                        {
                            "index": i + idx,  # Global index for tracking
                            "body": comment.get("body", "")[:500],  # Limit length
                            "score": comment.get("score", 0),
                        }
                    )

                comments_json = json.dumps(comments_data, indent=2)

                prompt = f"""You are a growth-focused investment analyst analyzing Reddit comments about {ticker.upper()}.

Post context: "{post_title}"

Comments to analyze (JSON array):
{comments_json}

For EACH comment, analyze the sentiment toward {ticker.upper()} in the context of the post.

Return a JSON array with one object per comment (same order), each containing:
{{
  "index": <comment_index>,
  "ticker": "{ticker.upper()}",
  "sentiment": "bullish" | "bearish" | "neutral",
  "confidence": 0.0-1.0,
  "score": -1.0 to +1.0,
  "fundamentals_score": 0.0-1.0,
  "potential_score": 0.0-1.0,
  "conviction_score": 0.0-1.0,
  "reasoning": "brief explanation",
  "catalysts": ["catalyst1", "catalyst2"],
  "risk_factors": ["risk1", "risk2"],
  "growth_drivers": ["driver1", "driver2"]
}}

IMPORTANT: Return ONLY a JSON array with exactly {len(batch)} objects, no explanation."""

                logger.debug(
                    f"🤖 Analyzing {len(batch)} comments in batch for ${ticker}",
                    extra={"ticker": ticker, "batch_size": len(batch)},
                )

                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a growth-focused investment analyst. Return valid JSON only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=self.temperature,
                    max_tokens=2000,  # More tokens for batch responses
                )

                result_text = response.choices[0].message.content
                if not result_text:
                    raise DataAdapterError(
                        "LLM returned empty response for batch comment analysis",
                        source=self.source,
                    )

                # Parse the JSON array response
                batch_data = json.loads(result_text)

                # Handle both array and object with "comments" key
                if isinstance(batch_data, dict):
                    batch_results = batch_data.get("comments", batch_data.get("results", []))
                else:
                    batch_results = batch_data

                # Convert each result to SentimentScore
                if batch_results:
                    for comment_result in batch_results:
                        try:
                            sentiment = SentimentScore(**comment_result)
                            results.append(sentiment)
                        except Exception as e:
                            logger.warning(
                                f"Failed to parse comment sentiment: {e}",
                                extra={"ticker": ticker, "error": str(e), "data": comment_result},
                            )

        except Exception as e:
            logger.error(
                f"Batch comment analysis failed for {ticker}: {e}",
                extra={"ticker": ticker, "error": str(e), "comments_count": len(comments)},
                exc_info=True,
            )
            # Fallback: return empty list, caller can retry individually if needed

        return results

    def analyze_batch(
        self,
        posts: list[dict[str, Any]],
        tickers_filter: list[str] | None = None,
        analyze_comments: bool = True,
        min_comment_score: int = 5,
    ) -> dict[str, list[SentimentScore]]:
        """Analyze sentiment for multiple posts (and their comments) grouped by ticker.

        Args:
            posts: List of post dicts (from RedditAdapter)
            tickers_filter: Optional list of tickers to analyze (others skipped)
            analyze_comments: Whether to also analyze comments for sentiment
            min_comment_score: Minimum comment score to analyze (filters low-quality comments)

        Returns:
            Dict mapping ticker -> list of SentimentScore objects

        Example:
            >>> posts = reddit_adapter.fetch_hot_posts("wallstreetbets", limit=50)
            >>> sentiments = analyzer.analyze_batch(posts, tickers_filter=["NVDA", "TSLA"])
            >>> sentiments["NVDA"]
            [SentimentScore(...), SentimentScore(...)]
        """
        results: dict[str, list[SentimentScore]] = {}

        # Track unique tickers for progress reporting
        all_tickers = set()
        for post in posts:
            tickers = post.get("tickers", [])
            if tickers_filter:
                tickers = [t for t in tickers if t in tickers_filter]
            all_tickers.update(tickers)

        ticker_preview = ", ".join(sorted(all_tickers)[:15])
        if len(all_tickers) > 15:
            ticker_preview += f"... (+{len(all_tickers) - 15} more)"

        logger.info(
            f"🔍 Found {len(all_tickers)} unique tickers mentioned: {ticker_preview}",
            unique_tickers=len(all_tickers),
        )

        processed_count = 0
        total_sentiments = 0
        total_comments_analyzed = 0
        total_posts = len(posts)

        for post_idx, post in enumerate(posts, 1):
            tickers = post.get("tickers", [])

            # Filter tickers if specified
            if tickers_filter:
                tickers = [t for t in tickers if t in tickers_filter]

            # Skip post if no relevant tickers
            if not tickers:
                continue

            # Log progress for this post
            logger.info(
                f'📄 Analyzing post {post_idx}/{total_posts}: "{post.get("title", "")[:80]}{"..." if len(post.get("title", "")) > 80 else ""}"',
                extra={
                    "post_index": post_idx,
                    "total_posts": total_posts,
                    "post_id": post.get("id"),
                    "tickers_in_post": tickers,
                },
            )

            # Analyze post sentiment for each ticker
            for ticker in tickers:
                try:
                    # Log progress for each ticker analysis
                    logger.info(f"🤖 Analyzing post sentiment for ${ticker}...", ticker=ticker)

                    sentiment = self.analyze_post(
                        ticker=ticker,
                        title=post.get("title", ""),
                        body=post.get("selftext", ""),
                        metadata={
                            "post_id": post.get("id"),
                            "score": post.get("score"),
                            "num_comments": post.get("num_comments"),
                        },
                    )

                    if ticker not in results:
                        results[ticker] = []
                    results[ticker].append(sentiment)
                    total_sentiments += 1
                    processed_count += 1

                    # Log result for this ticker
                    sentiment_emoji = (
                        "📈"
                        if sentiment.sentiment == "bullish"
                        else "📉"
                        if sentiment.sentiment == "bearish"
                        else "➡️"
                    )
                    logger.info(
                        f"{sentiment_emoji} ${ticker} (POST): {sentiment.sentiment.upper()} (score: {sentiment.score:+.2f}, confidence: {sentiment.confidence:.2f})",
                        ticker=ticker,
                        sentiment=sentiment.sentiment,
                        score=sentiment.score,
                        confidence=sentiment.confidence,
                        source="post",
                    )

                except DataAdapterError as e:
                    logger.warning(
                        f"⚠️ Failed to analyze ${ticker}: {str(e)}", ticker=ticker, error=str(e)
                    )
                    continue

            # Analyze comments ONCE per post (not per ticker)
            # Then distribute sentiment to tickers mentioned in each comment
            if analyze_comments and post.get("comments"):
                comments = post.get("comments", [])
                # Filter comments by minimum score only
                relevant_comments = [c for c in comments if c.get("score", 0) >= min_comment_score]

                if relevant_comments:
                    # Limit to top 15 comments to avoid excessive API costs
                    comments_to_analyze = relevant_comments[:15]

                    logger.info(
                        f"💬 Analyzing {len(comments_to_analyze)} comments ONCE (will distribute to mentioned tickers)...",
                        comments_count=len(comments_to_analyze),
                        post_tickers=tickers,
                    )

                    # Analyze ALL comments in context of ALL tickers in the post
                    # Use first ticker as "primary" for analysis context
                    primary_ticker = tickers[0]

                    try:
                        comment_sentiments = self.analyze_comments_batch(
                            ticker=primary_ticker,
                            post_title=post.get("title", ""),
                            comments=comments_to_analyze,
                            batch_size=10,  # Process 10 comments per API call
                        )

                        # Now distribute each comment's sentiment to relevant ticker(s)
                        for idx, (comment, sentiment) in enumerate(
                            zip(comments_to_analyze, comment_sentiments, strict=False), 1
                        ):
                            comment_body = comment.get("body", "")
                            comment_preview = (
                                comment_body[:150] + "..."
                                if len(comment_body) > 150
                                else comment_body
                            )

                            logger.info(
                                f'  💭 Comment {idx} (score: {comment.get("score", 0)}): "{comment_preview}"'
                            )

                            # Determine which ticker(s) this comment is about
                            mentioned_tickers = []
                            for ticker in tickers:
                                ticker_mentioned = (
                                    ticker.upper() in comment_body.upper()
                                    or f"${ticker.upper()}" in comment_body
                                )
                                if ticker_mentioned:
                                    mentioned_tickers.append(ticker)

                            # If no specific ticker mentioned, apply to all tickers in post
                            # (assume comment is about the post's topic)
                            if not mentioned_tickers and abs(sentiment.score) > 0.3:
                                mentioned_tickers = tickers

                            # Add sentiment to each mentioned ticker
                            for ticker in mentioned_tickers:
                                if ticker not in results:
                                    results[ticker] = []
                                results[ticker].append(sentiment)
                                total_sentiments += 1
                                total_comments_analyzed += 1

                                comment_emoji = (
                                    "📈"
                                    if sentiment.sentiment == "bullish"
                                    else ("📉" if sentiment.sentiment == "bearish" else "➡️")
                                )
                                logger.info(
                                    f"  {comment_emoji} ${ticker} Analysis: {sentiment.sentiment.upper()} (score: {sentiment.score:+.2f}, confidence: {sentiment.confidence:.2f})"
                                )

                    except Exception as e:
                        logger.error(
                            f"Batched comment analysis failed: {str(e)}",
                            error=str(e),
                        )

        logger.info(
            f"✅ Batch sentiment analysis complete - {total_sentiments} sentiments ({total_comments_analyzed} from comments) for {len(results)} tickers",
            posts_analyzed=len(posts),
            tickers_found=len(results),
            total_sentiments=total_sentiments,
            comment_sentiments=total_comments_analyzed,
        )

        return results

    def aggregate_sentiment(self, sentiments: list[SentimentScore]) -> dict[str, Any]:
        """Aggregate multiple sentiment scores into summary statistics.

        Args:
            sentiments: List of SentimentScore objects for the same ticker

        Returns:
            Dict with aggregated metrics (avg_score, bullish_ratio, etc.)

        Example:
            >>> sentiments = results["NVDA"]
            >>> agg = analyzer.aggregate_sentiment(sentiments)
            >>> agg["avg_score"]
            0.65
            >>> agg["bullish_ratio"]
            0.8
        """
        if not sentiments:
            return {
                "count": 0,
                "avg_score": 0.0,
                "avg_confidence": 0.0,
                "bullish_ratio": 0.0,
                "bearish_ratio": 0.0,
                "neutral_ratio": 0.0,
            }

        total = len(sentiments)
        bullish = sum(1 for s in sentiments if s.sentiment == "bullish")
        bearish = sum(1 for s in sentiments if s.sentiment == "bearish")
        neutral = sum(1 for s in sentiments if s.sentiment == "neutral")

        avg_score = sum(s.score for s in sentiments) / total
        avg_confidence = sum(s.confidence for s in sentiments) / total

        # Weighted score (score * confidence)
        weighted_scores = [s.score * s.confidence for s in sentiments]
        weighted_avg = sum(weighted_scores) / total if total > 0 else 0.0

        return {
            "count": total,
            "avg_score": round(avg_score, 3),
            "avg_confidence": round(avg_confidence, 3),
            "weighted_score": round(weighted_avg, 3),
            "bullish_ratio": round(bullish / total, 3),
            "bearish_ratio": round(bearish / total, 3),
            "neutral_ratio": round(neutral / total, 3),
            "sentiment_breakdown": {
                "bullish": bullish,
                "bearish": bearish,
                "neutral": neutral,
            },
        }

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Generic fetch method (delegates to analyze_post)."""
        return self.analyze_post(*args, **kwargs)

    def _build_attribution(self, **metadata: Any) -> Attribution:
        """Build attribution metadata for sentiment analysis.

        Args:
            **metadata: Additional metadata

        Returns:
            Attribution object
        """
        return Attribution(
            source=self.source,
            timestamp=datetime.now(UTC),
            url=None,
            api_endpoint=f"openai/{self.model}",
            version="1.0",
            metadata=metadata,
        )
