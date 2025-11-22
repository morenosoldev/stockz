"""Simple direct test of technical analysis with rate limiting."""

from datetime import date

from src.strategies.reddit_sentiment.implementation import RedditSentimentStrategy

print("Testing Technical Analysis with Rate Limiting\n")
print("=" * 60)

# Load strategy from config
strategy = RedditSentimentStrategy()

# Force enable technical analysis for testing
strategy.technical_analysis_enabled = True
strategy.technical_lookback_days = 30

print(f"Strategy loaded: {strategy.name}")
print(f"Technical Analysis Enabled: {strategy.technical_analysis_enabled}")
print(f"Technical Lookback Days: {strategy.technical_lookback_days}")
print()

print("=" * 60)
print("\nTesting technical analysis on 3 sample tickers...")
print("(Watch for the 5-second delay messages)\n")
print("=" * 60)

# Create fake candidate data for testing
test_candidates = [
    {"ticker": "AAPL", "weighted_score": 0.75, "mention_count": 10},
    {"ticker": "NVDA", "weighted_score": 0.80, "mention_count": 15},
    {"ticker": "TSLA", "weighted_score": 0.70, "mention_count": 8},
]

asof = date.today()

print(f"\nRunning technical analysis for {len(test_candidates)} tickers...")
print(f"Date: {asof}\n")

# Run the technical analysis method directly
strategy._run_technical_analysis(test_candidates, asof)

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)

# Check results
if strategy._technical_cache:
    print(f"\nSuccessfully analyzed {len(strategy._technical_cache)} tickers:")
    for ticker, data in strategy._technical_cache.items():
        analysis = data["analysis"]
        print(f"\n  {ticker}:")
        print(f"    Signal: {analysis.overall_signal}")
        print(f"    Strength: {analysis.signal_strength:.2f}")
        print(f"    Confidence: {analysis.confidence:.2f}")
        print(f"    Risk: {analysis.risk_assessment}")
else:
    print("\nNo technical analysis data generated (check for errors above)")

print("\nVerify that you saw:")
print("  1. Technical data fetched for each ticker")
print("  2. GPT-4 analysis for each ticker")
print("  3. '⏱️ Waiting 5 seconds...' message after each analysis")
print("  4. Approximately 10 seconds total delay (2 x 5 seconds)")
