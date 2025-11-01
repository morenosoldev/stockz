"""Aggregation and filtering of Reddit sentiment scores for tickers.

This module provides functions to aggregate sentiment scores for each ticker
across multiple Reddit posts, filter by mention count and confidence, and rank
candidates for strategy selection.
"""

from typing import Any

from src.datasources.sentiment import SentimentAnalyzer, SentimentScore
from src.ops.logging import get_logger

logger = get_logger(__name__)


def aggregate_ticker_sentiments(
    sentiments: dict[str, list[SentimentScore]],
    min_mentions: int = 2,
    min_confidence: float = 0.6,
    min_weighted_score: float = 0.2,
) -> list[dict[str, Any]]:
    """Aggregate and filter tickers by sentiment metrics.

    Args:
        sentiments: Dict[ticker, List[SentimentScore]]
        min_mentions: Minimum number of mentions to include ticker
        min_confidence: Minimum average confidence
        min_weighted_score: Minimum weighted score (bullish bias)

    Returns:
        List of candidate dicts with aggregated metrics and detailed LLM rationale
    """
    candidates = []
    analyzer = SentimentAnalyzer()

    logger.info(
        f"📊 Aggregating sentiment for {len(sentiments)} tickers...", ticker_count=len(sentiments)
    )

    for ticker, scores in sentiments.items():
        agg = analyzer.aggregate_sentiment(scores)

        # Collect detailed rationale from all sentiment analyses
        all_reasoning = []
        all_catalysts = []
        all_risk_factors = []
        sentiment_details = []

        for score in scores:
            # Collect reasoning from each analysis
            if score.reasoning:
                all_reasoning.append(score.reasoning)

            # Collect unique catalysts
            for catalyst in score.catalysts:
                if catalyst and catalyst not in all_catalysts:
                    all_catalysts.append(catalyst)

            # Collect unique risk factors
            for risk in score.risk_factors:
                if risk and risk not in all_risk_factors:
                    all_risk_factors.append(risk)

            # Store individual sentiment details for transparency
            sentiment_details.append(
                {
                    "sentiment": score.sentiment,
                    "score": score.score,
                    "confidence": score.confidence,
                    "reasoning": score.reasoning,
                    "catalysts": score.catalysts,
                    "risk_factors": score.risk_factors,
                }
            )

        # Log aggregation result for each ticker
        logger.info(
            f"📊 ${ticker}: {agg['count']} mentions, avg score {agg['avg_score']:+.2f}, weighted {agg['weighted_score']:+.2f}, confidence {agg['avg_confidence']:.2f}",
            ticker=ticker,
            mentions=agg["count"],
            avg_score=agg["avg_score"],
            weighted_score=agg["weighted_score"],
            avg_confidence=agg["avg_confidence"],
        )

        if (
            agg["count"] >= min_mentions
            and agg["avg_confidence"] >= min_confidence
            and agg["weighted_score"] >= min_weighted_score
        ):
            candidates.append(
                {
                    "ticker": ticker,
                    "mentions": agg["count"],
                    "avg_score": agg["avg_score"],
                    "weighted_score": agg["weighted_score"],
                    "avg_confidence": agg["avg_confidence"],
                    "bullish_ratio": agg["bullish_ratio"],
                    "bearish_ratio": agg["bearish_ratio"],
                    "neutral_ratio": agg["neutral_ratio"],
                    "sentiment_breakdown": agg["sentiment_breakdown"],
                    # Add detailed LLM rationale
                    "llm_rationale": {
                        "all_reasoning": all_reasoning,
                        "catalysts": all_catalysts,
                        "risk_factors": all_risk_factors,
                        "sentiment_details": sentiment_details,
                    },
                }
            )
            logger.info(
                f"✅ ${ticker} QUALIFIES (score: {agg['weighted_score']:+.2f}, {agg['count']} mentions)",
                ticker=ticker,
            )
        else:
            # Log why ticker was filtered out
            reasons = []
            if agg["count"] < min_mentions:
                reasons.append(f"only {agg['count']} mentions (need {min_mentions})")
            if agg["avg_confidence"] < min_confidence:
                reasons.append(f"confidence {agg['avg_confidence']:.2f} (need {min_confidence})")
            if agg["weighted_score"] < min_weighted_score:
                reasons.append(
                    f"score {agg['weighted_score']:+.2f} (need {min_weighted_score:+.2f})"
                )

            logger.info(f"❌ ${ticker} filtered out: {', '.join(reasons)}", ticker=ticker)

    # Sort candidates by weighted_score descending, then mentions
    candidates.sort(key=lambda x: (x["weighted_score"], x["mentions"]), reverse=True)

    logger.info(
        f"✅ Aggregation complete - {len(candidates)} qualifying candidates from {len(sentiments)} analyzed",
        total_candidates=len(candidates),
        total_analyzed=len(sentiments),
    )

    return candidates
