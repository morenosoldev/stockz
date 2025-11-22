#!/usr/bin/env python
"""Quick test of technical analysis with rate limiting.

This script tests the technical analysis feature by directly calling
the strategy with technical analysis enabled.
"""

import sys
from datetime import date
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.ops.logging import get_logger
from src.strategies.base import StrategyConfig
from src.strategies.reddit_sentiment.implementation import RedditSentimentStrategy

logger = get_logger(__name__)


def test_technical_analysis() -> None:
    """Test technical analysis with a small dataset."""
    logger.info("=" * 80)
    logger.info("🧪 TESTING TECHNICAL ANALYSIS WITH RATE LIMITING")
    logger.info("=" * 80)

    # Create minimal config for testing
    config = StrategyConfig(
        name="reddit_test",
        version="1.0.0",
        description="Test config",
        parameters={
            "sentiment_threshold": 0.5,
            "top_n": 3,  # Only top 3 candidates
            "subreddits": ["wallstreetbets"],  # Just one subreddit
            "posts_per_subreddit": 10,  # Only 10 posts
            "min_mentions": 1,
            "min_confidence": 0.5,
            "min_comment_score": 0,
            "require_catalysts": False,
            "cross_subreddit_boost": 0.1,
            "sentiment_analysis": {
                "model": "gpt-4o-mini",
                "temperature": 0.3,
                "max_tokens": 500,
                "scoring_weights": {
                    "fundamentals": 0.3,
                    "potential": 0.4,
                    "conviction": 0.3,
                },
                "min_conviction_threshold": 0.3,
                "potential_boost_threshold": 0.7,
            },
            "research_enabled": False,
            # ENABLE TECHNICAL ANALYSIS
            "technical_analysis_enabled": True,
            "technical_lookback_days": 30,
        },
        enabled=True,
    )

    logger.info("⚙️ Test Configuration:")
    logger.info("   - Technical Analysis: ENABLED ✅")
    logger.info("   - Posts per Subreddit: 10")
    logger.info("   - Top N Candidates: 3")
    logger.info("   - Subreddits: ['wallstreetbets']")
    logger.info("")
    logger.info("🚀 Starting scan...")
    logger.info("   (Watch for '⏱️ Waiting 5 seconds...' messages)")
    logger.info("")

    try:
        # Initialize strategy
        strategy = RedditSentimentStrategy(config)
        asof = date.today()

        # Run scan by getting universe and processing tickers
        logger.info("Getting candidate universe...")
        tickers = strategy.get_universe(asof=asof)

        logger.info(f"Found {len(tickers)} tickers to analyze")

        # Process each ticker through the strategy pipeline
        candidates = []
        for ticker in tickers[: config.parameters["top_n"]]:
            ticker_data = {"ticker": ticker, "asof": asof}
            if strategy.filters(ticker_data):
                features = strategy.features(ticker_data)
                score = strategy.score(features)
                candidates.append(
                    type(
                        "Candidate",
                        (),
                        {
                            "ticker": ticker,
                            "score": score,
                            "rationale": features.get("rationale", {}),
                        },
                    )()
                )

        logger.info("")
        logger.info("=" * 80)
        logger.info("✅ TEST COMPLETE!")
        logger.info("=" * 80)
        logger.info(f"📊 Found {len(candidates)} candidates with technical analysis")

        if candidates:
            logger.info("")
            logger.info("Top Candidates:")
            for i, candidate in enumerate(candidates[:5], 1):
                logger.info(f"  {i}. ${candidate.ticker} - Score: {candidate.score:.3f}")
                # Check if rationale has technical analysis
                if hasattr(candidate, "rationale") and candidate.rationale:
                    if "technical_analysis" in candidate.rationale:
                        tech = candidate.rationale["technical_analysis"]
                        logger.info(f"     📈 Technical Signal: {tech.get('signal', 'N/A')}")
                        logger.info(f"     💪 Signal Strength: {tech.get('strength', 0):.2f}")
                        logger.info(f"     🎯 Confidence: {tech.get('confidence', 0):.2f}")

        logger.info("")
        logger.info("🎯 Rate Limiting Verification:")
        logger.info("   ✅ Check the logs above for '⏱️ Waiting 5 seconds...' messages")
        logger.info("   ✅ Each technical analysis should have a 5-second delay")
        logger.info("   ✅ No rate limit errors should appear")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    test_technical_analysis()
