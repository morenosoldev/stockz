"""Unit tests for Reddit post pre-filtering functionality."""

from datetime import UTC, datetime
from unittest.mock import Mock

from src.datasources.reddit import RedditAdapter


class MockSubmission:
    """Mock PRAW Submission object for testing."""

    def __init__(self, title: str, selftext: str = "", link_flair_text: str = None):
        self.title = title
        self.selftext = selftext
        self.link_flair_text = link_flair_text
        self.id = "test123"
        self.score = 100
        self.num_comments = 10
        self.created_utc = datetime.now(UTC).timestamp()
        self.author = Mock()
        self.author.__str__ = Mock(return_value="testuser")
        self.url = "https://reddit.com/test"
        self.permalink = "/r/test/comments/test123"


class TestRedditPreFilter:
    """Test Reddit post pre-filtering."""

    def test_should_analyze_explicit_ticker(self):
        """Test that posts with explicit $TICKER format are analyzed."""
        adapter = RedditAdapter()

        post = MockSubmission(title="$AAPL calls going brrrr")
        assert adapter._should_analyze_post(post) is True

        post = MockSubmission(title="Thoughts on $TSLA?", selftext="Looking at $TSLA earnings")
        assert adapter._should_analyze_post(post) is True

    def test_should_analyze_uppercase_words(self):
        """Test that posts with multiple uppercase words are analyzed."""
        adapter = RedditAdapter()

        # Multiple uppercase words (likely tickers)
        post = MockSubmission(title="AAPL vs MSFT vs GOOGL comparison")
        assert adapter._should_analyze_post(post) is True

        # Single uppercase word - should skip
        post = MockSubmission(title="The market is crazy today")
        assert adapter._should_analyze_post(post) is False

    def test_should_analyze_stock_keywords(self):
        """Test that posts with stock keywords are analyzed."""
        adapter = RedditAdapter()

        # Stock keywords
        post = MockSubmission(title="Buy the dip on earnings beat")
        assert adapter._should_analyze_post(post) is True

        post = MockSubmission(title="DD: This stock will moon", selftext="Buying calls")
        assert adapter._should_analyze_post(post) is True

        # Single keyword - should skip (needs 2+)
        post = MockSubmission(title="I like this company")
        assert adapter._should_analyze_post(post) is False

    def test_should_skip_news_flair(self):
        """Test that news/politics flairs are skipped."""
        adapter = RedditAdapter()

        # News flair - skip even with keywords
        post = MockSubmission(
            title="Biden announces economic policy buy stocks", link_flair_text="News"
        )
        assert adapter._should_analyze_post(post) is False

        # Discussion flair - skip
        post = MockSubmission(title="General market discussion", link_flair_text="Discussion")
        assert adapter._should_analyze_post(post) is False

        # Politics - skip
        post = MockSubmission(title="$AAPL stock discussion", link_flair_text="Politics")
        assert adapter._should_analyze_post(post) is False

    def test_should_skip_generic_posts(self):
        """Test that generic posts without signals are skipped."""
        adapter = RedditAdapter()

        # No signals
        post = MockSubmission(title="What do you think about the market?")
        assert adapter._should_analyze_post(post) is False

        post = MockSubmission(title="Inflation is crazy")
        assert adapter._should_analyze_post(post) is False

        post = MockSubmission(title="The economy is doing well")
        assert adapter._should_analyze_post(post) is False

    def test_edge_cases(self):
        """Test edge cases."""
        adapter = RedditAdapter()

        # Empty title
        post = MockSubmission(title="")
        assert adapter._should_analyze_post(post) is False

        # Only selftext has signals
        post = MockSubmission(title="", selftext="$AAPL to the moon")
        assert adapter._should_analyze_post(post) is True

        # Mixed case ticker format
        post = MockSubmission(title="$aapl calls")
        assert adapter._should_analyze_post(post) is True

    def test_company_name_detection(self):
        """Test that company names are detected using spaCy NER."""
        adapter = RedditAdapter()

        # Netflix example (from user screenshot)
        post = MockSubmission(title="Netflix announces a 10-for-1 stock split")
        assert adapter._should_analyze_post(post) is True

        # Other company names
        post = MockSubmission(title="Apple just released new iPhone")
        assert adapter._should_analyze_post(post) is True

        post = MockSubmission(title="Tesla earnings call tomorrow")
        assert adapter._should_analyze_post(post) is True

        post = MockSubmission(title="Amazon CEO announces new initiative")
        assert adapter._should_analyze_post(post) is True

        # Not a company
        post = MockSubmission(title="I went to the store today")
        assert adapter._should_analyze_post(post) is False
