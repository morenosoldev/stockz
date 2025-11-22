"""Reddit data adapter for fetching posts and sentiment data.

This adapter uses the Reddit API (via PRAW) to fetch posts from specified
subreddits, focusing on stock-related discussions and sentiment.

All data fetched includes proper attribution and is cached to minimize API calls.
"""

import re
from datetime import UTC, datetime
from typing import Any

import praw
from praw.models import Submission

from src.datasources.attribution import Attribution
from src.datasources.base import (
    AuthenticationError,
    DataAdapterError,
    DataSource,
    RateLimitError,
)
from src.datasources.cache import CachedDataAdapter
from src.datasources.company_detector import CompanyDetector
from src.ops.config import get_config
from src.ops.logging import get_logger

logger = get_logger(__name__)


# Update DataSource enum to include Reddit
class RedditDataSource(str):
    """Reddit data source identifier."""

    REDDIT = "reddit"


class RedditAdapter(CachedDataAdapter):
    """Adapter for fetching data from Reddit using PRAW.

    This adapter provides methods to:
    - Fetch hot/top posts from subreddits
    - Extract ticker symbols from post titles/content
    - Get post metadata (score, comments, timestamps)
    - Fetch comments for sentiment analysis

    All data is cached with configurable TTL to minimize API calls.

    Attributes:
        source: Data source identifier (Reddit)
        reddit: PRAW Reddit instance
        cache_enabled: Whether caching is enabled
        cache_ttl: Cache time-to-live in seconds

    Example:
        >>> adapter = RedditAdapter()
        >>> posts = adapter.fetch_hot_posts("wallstreetbets", limit=100)
        >>> for post in posts:
        ...     print(post["ticker"], post["title"], post["score"])
    """

    source = DataSource.UNKNOWN  # Will be set to "reddit" in practice

    def __init__(
        self,
        cache_enabled: bool = True,
        cache_ttl: int | None = None,
    ) -> None:
        """Initialize Reddit adapter.

        Args:
            cache_enabled: Whether to enable caching (default: True)
            cache_ttl: Cache TTL in seconds (default: from config)

        Raises:
            AuthenticationError: If Reddit credentials are invalid
        """
        super().__init__(cache_enabled=cache_enabled, cache_ttl=cache_ttl)

        # Initialize attributes
        self.company_detector: CompanyDetector | None = None
        self._negative_cache: set[str] = set()

        # Get Reddit credentials from config
        config = get_config()
        client_id = config.datasources.reddit_client_id
        client_secret = config.datasources.reddit_client_secret
        user_agent = config.datasources.reddit_user_agent

        if not client_id or not client_secret or not user_agent:
            raise AuthenticationError(
                "Reddit API credentials not configured. "
                "Please set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, "
                "and REDDIT_USER_AGENT in .env file.",
                source=self.source,
            )

        # Initialize PRAW Reddit instance
        try:
            self.reddit = praw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
            )
            # Test connection
            self.reddit.read_only = True
            logger.info("Reddit API client initialized", extra={"user_agent": user_agent})
        except Exception as e:
            raise AuthenticationError(
                f"Failed to initialize Reddit API client: {e}",
                source=self.source,
                original_error=e,
            ) from e

        # Initialize CompanyDetector for pre-filtering (spaCy NER for organization detection)
        try:
            self.company_detector = CompanyDetector()
            logger.info("CompanyDetector initialized for pre-filtering")
        except Exception as e:
            logger.warning(
                f"Failed to initialize CompanyDetector for pre-filtering: {e}. "
                "Pre-filter will skip company name detection.",
                extra={"error": str(e)},
            )
            self.company_detector = None

    def fetch_hot_posts(
        self,
        subreddit: str,
        limit: int = 100,
        time_filter: str = "day",
        include_comments: bool = True,
        comments_limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Fetch hot posts from a subreddit with optional comments.

        Args:
            subreddit: Subreddit name (e.g., "wallstreetbets")
            limit: Maximum number of posts to fetch (max: 100)
            time_filter: Time filter ("day", "week", "month", "year", "all")
            include_comments: Whether to fetch top comments for each post
            comments_limit: Maximum number of top comments per post

        Returns:
            List of post dictionaries with metadata, extracted tickers, and optional comments

        Raises:
            DataAdapterError: If fetching fails
            RateLimitError: If rate limit is exceeded
        """
        cache_key = f"reddit_hot_{subreddit}_{limit}_{time_filter}_comments{comments_limit if include_comments else 0}"

        # Try cache first
        if self.cache_enabled:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                logger.debug(
                    "Reddit posts fetched from cache",
                    extra={"subreddit": subreddit, "limit": limit},
                )
                return cached

        # Fetch from API
        try:
            sub = self.reddit.subreddit(subreddit)
            posts_raw = list(sub.hot(limit=limit))

            posts = []
            posts_skipped = 0
            for post in posts_raw:
                # Pre-filter: Skip posts that don't show stock signals
                if not self._should_analyze_post(post):
                    posts_skipped += 1
                    continue

                parsed_post = self._parse_submission(post)

                # Fetch comments if requested
                if include_comments and post.num_comments > 0:
                    try:
                        # Expand comment tree (limit=0 means don't fetch nested "load more" comments)
                        # This fetches top-level comments only
                        post.comments.replace_more(limit=0)

                        # Get all top-level comments and flatten the list
                        all_comments = list(post.comments)

                        # Filter out non-comment objects and sort by score
                        valid_comments = [
                            c for c in all_comments if hasattr(c, "body") and hasattr(c, "score")
                        ]
                        valid_comments.sort(key=lambda c: c.score, reverse=True)

                        # Take top N comments by score
                        top_comments = valid_comments[:comments_limit]

                        comments = []
                        for comment in top_comments:
                            comments.append(
                                {
                                    "id": comment.id,
                                    "body": comment.body,
                                    "score": comment.score,
                                    "created_utc": datetime.fromtimestamp(
                                        comment.created_utc, tz=UTC
                                    ),
                                    "author": (
                                        str(comment.author) if comment.author else "[deleted]"
                                    ),
                                }
                            )

                        parsed_post["comments"] = comments
                        parsed_post["comments_analyzed"] = len(comments)

                        logger.debug(
                            f"Fetched {len(comments)} comments for post {post.id}",
                            extra={
                                "post_id": post.id,
                                "total_comments": post.num_comments,
                                "fetched": len(all_comments),
                                "valid": len(valid_comments),
                                "selected": len(comments),
                            },
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch comments for post {post.id}: {e}",
                            extra={"post_id": post.id, "error": str(e)},
                        )
                        parsed_post["comments"] = []
                        parsed_post["comments_analyzed"] = 0
                else:
                    parsed_post["comments"] = []
                    parsed_post["comments_analyzed"] = 0

                posts.append(parsed_post)

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://reddit.com/r/{subreddit}/hot",
                metadata={
                    "subreddit": subreddit,
                    "limit": limit,
                    "time_filter": time_filter,
                    "posts_fetched": len(posts),
                    "include_comments": include_comments,
                    "comments_limit": comments_limit if include_comments else 0,
                },
            )

            # Cache results
            if self.cache_enabled:
                self._save_to_cache(cache_key, posts)

            total_comments = sum(p["comments_analyzed"] for p in posts)
            filter_rate = (posts_skipped / len(posts_raw) * 100) if posts_raw else 0
            logger.info(
                f"Fetched {len(posts)} Reddit posts with {total_comments} comments "
                f"(filtered out {posts_skipped}/{len(posts_raw)} posts, {filter_rate:.1f}%)",
                extra={
                    "subreddit": subreddit,
                    "posts": len(posts),
                    "posts_skipped": posts_skipped,
                    "posts_total": len(posts_raw),
                    "filter_rate_pct": filter_rate,
                    "comments": total_comments,
                    "limit": limit,
                },
            )

            return posts

        except praw.exceptions.PRAWException as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                raise RateLimitError(
                    f"Reddit API rate limit exceeded: {e}",
                    source=self.source,
                    original_error=e,
                ) from e
            raise DataAdapterError(
                f"Failed to fetch Reddit posts: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def fetch_top_posts(
        self,
        subreddit: str,
        limit: int = 100,
        time_filter: str = "day",
    ) -> list[dict[str, Any]]:
        """Fetch top posts from a subreddit.

        Args:
            subreddit: Subreddit name (e.g., "wallstreetbets")
            limit: Maximum number of posts to fetch (max: 100)
            time_filter: Time filter ("day", "week", "month", "year", "all")

        Returns:
            List of post dictionaries with metadata and extracted tickers

        Raises:
            DataAdapterError: If fetching fails
            RateLimitError: If rate limit is exceeded
        """
        cache_key = f"reddit_top_{subreddit}_{limit}_{time_filter}"

        # Try cache first
        if self.cache_enabled:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                logger.debug(
                    "Reddit posts fetched from cache",
                    extra={"subreddit": subreddit, "limit": limit},
                )
                return cached

        # Fetch from API
        try:
            sub = self.reddit.subreddit(subreddit)
            posts_raw = list(sub.top(time_filter=time_filter, limit=limit))

            posts = [self._parse_submission(post) for post in posts_raw]

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://reddit.com/r/{subreddit}/top?t={time_filter}",
                metadata={
                    "subreddit": subreddit,
                    "limit": limit,
                    "time_filter": time_filter,
                    "posts_fetched": len(posts),
                },
            )

            # Cache results
            if self.cache_enabled:
                self._save_to_cache(cache_key, posts)

            logger.info(
                "Fetched Reddit top posts",
                extra={
                    "subreddit": subreddit,
                    "posts": len(posts),
                    "limit": limit,
                    "time_filter": time_filter,
                },
            )

            return posts

        except praw.exceptions.PRAWException as e:
            if "429" in str(e) or "rate limit" in str(e).lower():
                raise RateLimitError(
                    f"Reddit API rate limit exceeded: {e}",
                    source=self.source,
                    original_error=e,
                ) from e
            raise DataAdapterError(
                f"Failed to fetch Reddit top posts: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def fetch_comments(
        self,
        post_id: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch top-level comments from a post.

        Args:
            post_id: Reddit post ID
            limit: Maximum number of comments to fetch

        Returns:
            List of comment dictionaries with metadata

        Raises:
            DataAdapterError: If fetching fails
        """
        cache_key = f"reddit_comments_{post_id}_{limit}"

        # Try cache first
        if self.cache_enabled:
            cached = self._get_from_cache(cache_key)
            if cached is not None:
                return cached

        # Fetch from API
        try:
            submission = self.reddit.submission(id=post_id)
            submission.comments.replace_more(limit=0)  # Don't fetch "load more" comments

            comments = []
            for comment in list(submission.comments)[:limit]:
                comments.append(
                    {
                        "id": comment.id,
                        "body": comment.body,
                        "score": comment.score,
                        "created_utc": datetime.fromtimestamp(comment.created_utc, tz=UTC),
                        "author": str(comment.author) if comment.author else "[deleted]",
                    }
                )

            # Build attribution
            self._last_attribution = self._build_attribution(
                url=f"https://reddit.com/comments/{post_id}",
                metadata={
                    "post_id": post_id,
                    "comments_fetched": len(comments),
                },
            )

            # Cache results
            if self.cache_enabled:
                self._save_to_cache(cache_key, comments)

            return comments

        except praw.exceptions.PRAWException as e:
            raise DataAdapterError(
                f"Failed to fetch Reddit comments: {e}",
                source=self.source,
                original_error=e,
            ) from e

    def _should_analyze_post(self, submission: Submission) -> bool:
        """Pre-filter: Check if post is likely to contain stock discussions.

        This filters out posts about general economics, politics, news, etc.
        that don't mention specific stocks. Reduces unnecessary AI processing.

        Filters (in priority order):
        1. **Flair filtering** (HIGHEST PRIORITY): Skip flairs like "News", "Discussion", "Politics"
        2. **Options gambling/loss porn**: Skip posts with "call/calls/put/puts/loss/yolo" in title
        3. **Explicit ticker mentions**: $TICKER format (e.g., $AAPL, $TSLA)
        4. **Uppercase words**: 2-5 letter words that could be tickers
        5. **Stock-related keywords**: "buy", "sell", "DD", "position", "shares", "stock"
        6. **Company name detection**: Uses spaCy NER to detect organization mentions (e.g., "Netflix", "Apple")

        Args:
            submission: PRAW Submission object

        Returns:
            True if post should be analyzed, False if should skip

        Example:
            "Biden announces new economic policy" [News flair] → False (skip)
            "Inflation hits 7% - what this means for markets" → False (skip)
            "Trader puts his college tuition on MSFT calls and loses it all" → False (skip - gambling)
            "Just bought 1000 shares of $AAPL - here's my DD" → True (analyze)
            "TSLA earnings call tomorrow - bullish?" → True (analyze - "earnings call" is different from options)
            "Netflix announces a 10-for-1 stock split" → True (analyze - NER detects "Netflix")
        """
        # 1. FIRST: Filter out by flair (skip general discussion, news, politics)
        #    This is checked FIRST to skip these posts regardless of content
        skip_flairs = {
            "news",
            "discussion",
            "politics",
            "general",
            "economy",
            "economics",
            "market",
            "general discussion",
            "daily discussion",
            "weekend discussion",
        }
        if submission.link_flair_text and submission.link_flair_text.lower() in skip_flairs:
            logger.debug(
                f"⏭️ Skipping post - flair '{submission.link_flair_text}' is not stock-specific",
                extra={"post_id": submission.id, "title": submission.title[:50]},
            )
            return False

        # 2. Filter out options gambling and loss porn posts (prevents analyzing irrelevant content)
        #    Check the TITLE specifically, as these posts often have misleading titles
        title_lower = submission.title.lower()

        # Skip if "earnings call" - this is legitimate stock discussion
        if "earnings call" in title_lower:
            pass  # Don't filter, continue to other checks
        else:
            gambling_keywords = [
                # Options gambling (using spaces to avoid matching "call" in "earnings call")
                " call ",
                " calls ",
                " put ",
                " puts ",
                "call and",
                "calls and",
                "put and",
                "puts and",
                "call or",
                "calls or",
                "put or",
                "puts or",
                # Loss porn
                "loss",
                "loses",
                "lost",
                "yolo",
                "rip",
                "down bad",
                "blew up",
                "wiped out",
            ]
            if any(keyword in title_lower for keyword in gambling_keywords):
                logger.debug(
                    "⏭️ Skipping post - likely options gambling/loss porn",
                    extra={"post_id": submission.id, "title": submission.title[:80]},
                )
                return False

        text = (submission.title + " " + (submission.selftext or "")).lower()

        # 3. Check for explicit $TICKER mentions (strong signal)
        if re.search(r"\$[A-Z]{1,5}\b", submission.title + " " + (submission.selftext or "")):
            logger.debug(
                "✅ Post has explicit ticker ($TICKER) - analyzing",
                extra={"post_id": submission.id, "title": submission.title[:50]},
            )
            return True

        # 4. Check for uppercase ticker-like words (medium signal)
        uppercase_words = re.findall(
            r"\b([A-Z]{2,5})\b", submission.title + " " + (submission.selftext or "")
        )
        # Filter out common non-ticker words
        non_ticker_words = {
            "WSB",
            "DD",
            "CEO",
            "CFO",
            "IPO",
            "ETF",
            "USA",
            "US",
            "UK",
            "EU",
            "GDP",
            "CPI",
            "FBI",
            "SEC",
            "FDA",
        }
        potential_tickers = [w for w in uppercase_words if w not in non_ticker_words]
        if len(potential_tickers) >= 2:  # At least 2 potential tickers
            logger.debug(
                f"✅ Post has {len(potential_tickers)} uppercase words - analyzing",
                extra={
                    "post_id": submission.id,
                    "title": submission.title[:50],
                    "words": potential_tickers[:5],
                },
            )
            return True

        # 5. Check for stock-related keywords (strong signal)
        stock_keywords = {
            # Trading actions
            "buy",
            "bought",
            "sell",
            "sold",
            "long",
            "short",
            "position",
            "holdings",
            "portfolio",
            # Options
            "call",
            "calls",
            "put",
            "puts",
            "strike",
            "expiry",
            "options",
            # Stock terms
            "shares",
            "stock",
            "ticker",
            "earnings",
            "dd",
            "due diligence",
            "analysis",
            "valuation",
            "fundamentals",
            "technicals",
            "chart",
            # Sentiment
            "bullish",
            "bearish",
            "moon",
            "squeeze",
            "dip",
            "rally",
            "breakout",
            # YOLO/WSB specific
            "yolo",
            "gains",
            "loss",
            "tendies",
            "diamond hands",
            "paper hands",
        }
        keywords_found = [kw for kw in stock_keywords if kw in text]
        if len(keywords_found) >= 2:  # At least 2 stock keywords
            logger.debug(
                f"✅ Post has {len(keywords_found)} stock keywords - analyzing",
                extra={
                    "post_id": submission.id,
                    "title": submission.title[:50],
                    "keywords": keywords_found[:5],
                },
            )
            return True

        # 6. Check for company/organization mentions using spaCy NER (catches "Netflix", "Apple", etc.)
        if self.company_detector:
            try:
                # Extract company names from title + selftext using spaCy NER
                full_text = submission.title + " " + (submission.selftext or "")

                # Clean text before NER to avoid URL fragments and Markdown syntax
                # 1. Remove complete Markdown links: [text](url) → text
                # 2. Remove Markdown images: ![alt](url) → alt
                # 3. Remove standalone URLs (https://... or http://...)
                # 4. Clean up broken Markdown syntax (leftover '](' from partial links)
                cleaned_text = re.sub(
                    r"\[([^\]]+)\]\([^\)]+\)", r"\1", full_text
                )  # [text](url) → text
                cleaned_text = re.sub(
                    r"!\[([^\]]*)\]\([^\)]+\)", r"\1", cleaned_text
                )  # ![alt](url) → alt
                cleaned_text = re.sub(r"https?://\S+", "", cleaned_text)  # Remove URLs
                cleaned_text = re.sub(r"\]\([^\)]*\)", "", cleaned_text)  # Remove broken ](...)
                cleaned_text = re.sub(r"\]\(", "", cleaned_text)  # Remove broken ](

                company_names = self.company_detector.extract_company_names(cleaned_text)

                # If any organization entities found, analyze the post
                if company_names:
                    logger.debug(
                        f"✅ Post mentions {len(company_names)} organization(s) - analyzing",
                        extra={
                            "post_id": submission.id,
                            "title": submission.title[:50],
                            "organizations": company_names[:3],
                        },
                    )
                    return True
            except Exception as e:
                logger.warning(
                    f"Error in company detection during pre-filter: {e}",
                    extra={"post_id": submission.id, "error": str(e)},
                )
                # Continue to other checks if NER fails

        # If none of the signals matched, skip (likely general discussion)
        logger.debug(
            "⏭️ Skipping post - no stock signals detected",
            extra={"post_id": submission.id, "title": submission.title[:50]},
        )
        return False

    def _parse_submission(self, submission: Submission) -> dict[str, Any]:
        """Parse a PRAW submission into a standardized dictionary.

        Args:
            submission: PRAW Submission object

        Returns:
            Dictionary with post metadata and extracted tickers
        """
        # Extract ticker symbols from title and selftext
        tickers = self._extract_tickers(submission.title + " " + (submission.selftext or ""))

        return {
            "id": submission.id,
            "title": submission.title,
            "selftext": submission.selftext or "",
            "score": submission.score,
            "upvote_ratio": submission.upvote_ratio,
            "num_comments": submission.num_comments,
            "created_utc": datetime.fromtimestamp(submission.created_utc, tz=UTC),
            "author": str(submission.author) if submission.author else "[deleted]",
            "url": submission.url,
            "permalink": f"https://reddit.com{submission.permalink}",
            "tickers": tickers,
            "link_flair_text": submission.link_flair_text,
        }

    def _extract_tickers(self, text: str) -> list[str]:
        """Extract ticker symbols from text using hybrid regex + AI pipeline.

        Pipeline:
        1. **Regex Path (Fast)**: Extract $TICKER and standalone uppercase words
        2. **AI Path (Slow)**: NER → LLM → yfinance validation for company names

        Args:
            text: Text to extract tickers from

        Returns:
            List of unique ticker symbols (uppercase)

        Example:
            Text: "Apple crushed earnings! $MSFT also beat. Gubra trial promising."
            Regex: ["MSFT"]
            AI: ["AAPL", "GUBRA.CO"]
            Combined: ["AAPL", "GUBRA.CO", "MSFT"]
        """
        from src.datasources.company_detector import CompanyDetector
        from src.datasources.ticker_validator import TickerValidator

        # Use the CompanyDetector initialized in __init__ (already has API key)
        # Fall back to creating a new one only if not available
        if not self.company_detector:
            logger.warning("CompanyDetector not available from init, creating new instance")
            self.company_detector = CompanyDetector()

        # Initialize ticker validator if not already done (lazy-load)
        if not hasattr(self, "_ticker_validator"):
            self._ticker_validator = TickerValidator()

        # ═══════════════════════════════════════════════════════════════
        # REGEX PATH (Fast - Explicit Tickers)
        # ═══════════════════════════════════════════════════════════════

        # Expanded blacklist to exclude common abbreviations that aren't tickers
        # Applies to BOTH $TICKER and standalone patterns
        TICKER_BLACKLIST = {
            # Original common words
            "A",
            "I",
            "THE",
            "WSB",
            "DD",
            "YOLO",
            "CEO",
            "CFO",
            "IPO",
            "ETF",
            "FD",
            "TA",
            "IV",
            # Financial/Economic Terms (Phase 1 + 2)
            "YOY",
            "QOQ",
            "MOM",
            "WOW",
            "GDP",
            "CPI",
            "PPI",
            "API",
            "EPS",
            "PE",
            "PS",
            "PB",
            "ROE",
            "ROI",
            "ROA",
            "EBIT",
            "EBITDA",
            "FCF",
            "NPV",
            "IRR",
            "CAGR",
            "YTD",
            "MTD",
            "QTD",
            "ATH",
            "ATL",
            "AH",
            "PM",
            "Q1",
            "Q2",
            "Q3",
            "Q4",  # Quarterly abbreviations
            "MAG7",  # Magnificent 7
            # Market Terms (Phase 1)
            "NYSE",
            "NASDAQ",
            "AMEX",
            "OTC",
            "DOW",
            "SPX",
            "SPY",
            "QQQ",
            "VIX",
            "DIA",
            "IWM",
            "DJI",
            "RUT",
            # Reddit/Trading Slang (Phase 1)
            "FOMO",
            "FUD",
            "HODL",
            "IMO",
            "IMHO",
            "TBH",
            "NGL",
            "BTW",
            "FYI",
            "PSA",
            "TIL",
            "ELI5",
            "TLDR",
            "AMA",
            "ITM",
            "OTM",
            "GUH",
            "BTFD",
            "GG",
            "GL",
            "RIP",
            "LFG",
            "GME",
            "AMC",
            # Time/Date Abbreviations (Phase 1)
            "AM",
            "EST",
            "PST",
            "CST",
            "MST",
            "UTC",
            "GMT",
            "MON",
            "TUE",
            "WED",
            "THU",
            "FRI",
            "SAT",
            "SUN",
            "JAN",
            "FEB",
            "MAR",
            "APR",
            "MAY",
            "JUN",
            "JUL",
            "AUG",
            "SEP",
            "OCT",
            "NOV",
            "DEC",
            # Organizations/Government (Phase 1 + 2)
            "USA",
            "US",
            "UK",
            "EU",
            "UN",
            "SEC",
            "FDA",
            "DOJ",
            "FBI",
            "IRS",
            "EPA",
            "FTC",
            "DOD",
            "CIA",
            "NSA",
            "OSHA",
            "FED",  # Federal Reserve
            # Technology/General (Phase 1 + 2)
            "IT",
            "AI",
            "ML",
            "AR",
            "VR",
            "IOT",
            "SaaS",
            "SDK",
            "AWS",
            "UI",
            "UX",
            "SEO",
            "CRM",
            "ERP",
            "BI",
            # Common Expressions (Phase 1)
            "LOL",
            "LMAO",
            "WTF",
            "OMG",
            "IDK",
            "AFAIK",
            "IIRC",
            "SMH",
            "TY",
            "NP",
            "OP",
            "DM",
            "DMs",
            "NSFW",
            "SFW",
            # Common words that appear with $ prefix (Phase 2)
            "HOLD",
            "LEAPS",
            "NEW",
            "THIS",
            "CALLS",
            "PUTS",
            "CAN",
            "LOVE",
            "LOYAL",
            "NOW",
            "OF",
            "PRIME",
            "YEAR",
            "YOU",
            "E",
            "P",
            "V",
            "GH",
            "ER",
            "LA",
            "FAANG",
            "HHI",
            "HYSA",
            "BEZOS",
        }

        # Pattern 1: $TICKER format (filter blacklist)
        dollar_tickers = [
            ticker
            for ticker in re.findall(r"\$([A-Z]{1,5})\b", text)
            if ticker not in TICKER_BLACKLIST
        ]

        # Pattern 2: Standalone uppercase words (1-5 chars, filter blacklist)
        word_tickers = [
            word for word in re.findall(r"\b([A-Z]{1,5})\b", text) if word not in TICKER_BLACKLIST
        ]

        # Combine regex results
        regex_tickers = set(dollar_tickers + word_tickers)

        # Validate regex tickers (format + blacklist check)
        validated_regex_tickers = {
            ticker for ticker in regex_tickers if self._ticker_validator.is_likely_stock(ticker)
        }

        logger.debug(
            f"Regex extraction found {len(validated_regex_tickers)} tickers",
            extra={
                "regex_tickers": sorted(validated_regex_tickers),
                "rejected": sorted(regex_tickers - validated_regex_tickers),
            },
        )

        # ═══════════════════════════════════════════════════════════════
        # AI PATH (Slow - Company Names → Tickers)
        # ═══════════════════════════════════════════════════════════════

        ai_tickers = set()

        # P6: Generic term blacklist (lowercase for case-insensitive matching)
        GENERIC_BLACKLIST = {
            "company",
            "companies",
            "corp",
            "corporation",
            "incorporated",
            "limited",
            "group",
            "holdings",
            "ventures",
            "capital",
            "partners",
            "fund",
            "trust",
            "bank",
            "financial",
            "been",
            "penny",
            "daily",
            "discussion",
            "fundamentals",
            "veterans",
            "westinghouse",  # From observed false positives
        }

        try:
            # Clean text before NER to avoid URL fragments and Markdown syntax
            # 1. Remove complete Markdown links: [text](url) → text
            # 2. Remove Markdown images: ![alt](url) → alt
            # 3. Remove standalone URLs (https://... or http://...)
            # 4. Clean up broken Markdown syntax (leftover '](' from partial links)
            cleaned_text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)  # [text](url) → text
            cleaned_text = re.sub(
                r"!\[([^\]]*)\]\([^\)]+\)", r"\1", cleaned_text
            )  # ![alt](url) → alt
            cleaned_text = re.sub(r"https?://\S+", "", cleaned_text)  # Remove URLs
            cleaned_text = re.sub(r"\]\([^\)]*\)", "", cleaned_text)  # Remove broken ](...)
            cleaned_text = re.sub(r"\]\(", "", cleaned_text)  # Remove broken ](

            # Stage 1: Extract company names using NER
            company_names = self.company_detector.extract_company_names(cleaned_text)

            # P3: Deduplicate company names to avoid redundant LLM calls
            # Remove duplicates and possessive variants (e.g., "Warner Bros" and "Warner Bros Discovery's")
            unique_companies = set()
            for name in company_names:
                # Strip possessive endings
                clean_name = name.rstrip("'s").rstrip("'")
                unique_companies.add(clean_name)

            # P2: Min length filter - skip very short names unless all caps (like IBM, AMD)
            filtered_companies = []
            for name in unique_companies:
                # Skip if < 4 chars and not all uppercase
                if len(name) < 4 and not name.isupper():
                    logger.debug(
                        "Skipped short name (P2 min length filter)",
                        extra={"company_name": name, "length": len(name)},
                    )
                    continue

                # Skip generic words
                if name.lower() in GENERIC_BLACKLIST:
                    logger.debug(
                        "Skipped generic term (P2 generic blacklist)", extra={"company_name": name}
                    )
                    continue

                # P6: Skip if in negative cache
                if name.lower() in self._negative_cache:
                    logger.debug(
                        "Skipped cached rejection (P6 negative cache)", extra={"company_name": name}
                    )
                    continue

                filtered_companies.append(name)

            if filtered_companies:
                logger.debug(
                    f"NER detected {len(filtered_companies)} valid companies (after P2/P3/P6 filters)",
                    extra={
                        "original_count": len(company_names),
                        "deduplicated_count": len(unique_companies),
                        "filtered_count": len(filtered_companies),
                        "companies": filtered_companies,
                    },
                )

                # P5: Batch LLM calls for efficiency (10 companies per API call)
                batch_results = self.company_detector.resolve_to_tickers_batch(
                    filtered_companies, batch_size=10
                )

                # Stage 2 & 3: Process batch results
                for company_name, resolution in batch_results.items():
                    # Skip if already found by regex
                    if (
                        resolution
                        and resolution.get("ticker")
                        and resolution["ticker"].upper() in validated_regex_tickers
                    ):
                        continue

                    if resolution and resolution.get("ticker"):
                        ticker = resolution["ticker"]

                        # Validate ticker using market data adapter
                        # Re-enabled with Twelve Data migration (reliable API)
                        validate_ticker = True

                        if validate_ticker:
                            # Market data adapter: Does this ticker actually exist?
                            if self.company_detector.validate_ticker(ticker):
                                ai_tickers.add(ticker)
                                logger.info(
                                    "✅ AI pipeline resolved company to ticker",
                                    extra={
                                        "company_name": company_name,
                                        "ticker": ticker,
                                        "exchange": resolution.get("exchange"),
                                        "pipeline": "NER→LLM(batch)→yfinance",
                                    },
                                )
                            else:
                                logger.warning(
                                    "❌ LLM-suggested ticker failed yfinance validation",
                                    extra={
                                        "company_name": company_name,
                                        "ticker": ticker,
                                        "stage": "yfinance_validation",
                                    },
                                )
                        else:
                            # Skip validation, trust LLM
                            ai_tickers.add(ticker)
                            logger.info(
                                "✅ AI pipeline resolved company to ticker (yfinance validation skipped)",
                                extra={
                                    "company_name": company_name,
                                    "ticker": ticker,
                                    "exchange": resolution.get("exchange"),
                                    "pipeline": "NER→LLM(batch)",
                                },
                            )
                    else:
                        # P6: Add to negative cache to avoid re-querying
                        self._negative_cache.add(company_name.lower())
                        logger.debug(
                            "LLM rejected company (not publicly traded) - added to negative cache",
                            extra={"company_name": company_name},
                        )

        except Exception as e:
            logger.error(
                f"AI ticker extraction failed: {e}", extra={"error": str(e)}, exc_info=True
            )
            # Fallback to regex-only results if AI fails

        # ═══════════════════════════════════════════════════════════════
        # COMBINE & RETURN
        # ═══════════════════════════════════════════════════════════════

        all_tickers = validated_regex_tickers | ai_tickers

        logger.debug(
            "Final ticker extraction complete",
            extra={
                "total_tickers": len(all_tickers),
                "regex_count": len(validated_regex_tickers),
                "ai_count": len(ai_tickers),
                "tickers": sorted(all_tickers),
            },
        )

        return sorted(all_tickers)

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        """Generic fetch method (delegates to fetch_hot_posts).

        Args:
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from fetch_hot_posts
        """
        return self.fetch_hot_posts(*args, **kwargs)

    def _build_attribution(self, **metadata: Any) -> Attribution:
        """Build attribution metadata for Reddit data.

        Args:
            **metadata: Additional metadata

        Returns:
            Attribution object
        """
        return Attribution(
            source=DataSource.UNKNOWN,  # Would be "reddit" in practice
            timestamp=datetime.now(UTC),
            version="1.0",
            metadata=metadata,
        )
