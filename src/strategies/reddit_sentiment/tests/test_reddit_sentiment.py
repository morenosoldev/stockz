from src.strategies.base import StrategyConfig
from src.strategies.reddit_sentiment.implementation import (
    RedditSentimentStrategy,
    get_candidates,
)


def test_filters() -> None:
    config = StrategyConfig(
        name="reddit",
        version="1.0.0",
        description="Test",
        enabled=True,
        parameters={"sentiment_threshold": 0.5},
    )
    strat = RedditSentimentStrategy(config=config)
    assert strat.filters({"sentiment": 0.6})
    assert not strat.filters({"sentiment": 0.4})


def test_score() -> None:
    strat = RedditSentimentStrategy()
    assert strat.score({"sentiment": 0.8}) == 0.8
    assert strat.score({"sentiment": -0.2}) == 0.0
    assert strat.score({"sentiment": 1.2}) == 1.0


def test_get_candidates() -> None:
    result = get_candidates(top_n=5)
    assert "candidates" in result
    assert "strategy" in result
