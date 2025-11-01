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
            for post in posts_raw:
                parsed_post = self._parse_submission(post)

                # Fetch comments if requested
                if include_comments and post.num_comments > 0:
                    try:
                        post.comments.replace_more(limit=0)  # Don't fetch "load more" comments
                        comments = []
                        for comment in list(post.comments)[:comments_limit]:
                            if hasattr(comment, "body"):  # Ensure it's a comment, not MoreComments
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
                        # Sort by score descending to get highest quality comments first
                        comments.sort(key=lambda c: c["score"], reverse=True)
                        parsed_post["comments"] = comments
                        parsed_post["comments_analyzed"] = len(comments)
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
            logger.info(
                f"Fetched {len(posts)} Reddit posts with {total_comments} comments",
                extra={
                    "subreddit": subreddit,
                    "posts": len(posts),
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
        """Extract ticker symbols from text.

        Uses regex to find patterns like $AAPL or standalone uppercase words
        that look like ticker symbols (1-5 characters).

        Args:
            text: Text to extract tickers from

        Returns:
            List of unique ticker symbols (uppercase)
        """
        # Pattern 1: $TICKER format
        dollar_tickers = re.findall(r"\$([A-Z]{1,5})\b", text)

        # Pattern 2: Standalone uppercase words (1-5 chars)
        # Exclude common words that aren't tickers
        common_words = {
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
        }
        word_tickers = [
            word for word in re.findall(r"\b([A-Z]{1,5})\b", text) if word not in common_words
        ]

        # Combine and deduplicate
        all_tickers = list(set(dollar_tickers + word_tickers))

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
