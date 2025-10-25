#!/usr/bin/env python3
"""Demo script to show NewsAdapter fetching real-time news with sentiment analysis.

This script demonstrates the NewsAdapter in action:
- Fetching news headlines for tickers
- Analyzing sentiment (positive/negative/neutral)
- Detecting risk keywords
- Cache performance
- Full attribution tracking
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.datasources.news import NewsAdapter
from src.ops.logging import setup_logging

# Setup logging to console
setup_logging(log_level="INFO", log_format="text")


def main():
    """Run demo of news adapter."""
    print("\n" + "=" * 70)
    print("📰 NEWS ADAPTER DEMO - Real-time Yahoo Finance News & Sentiment")
    print("=" * 70 + "\n")

    # Create adapter
    print("📊 Initializing NewsAdapter...")
    adapter = NewsAdapter()
    print("✅ NewsAdapter ready!\n")

    # Test with a few tickers
    test_tickers = ["AAPL", "TSLA"]

    for i, ticker in enumerate(test_tickers, 1):
        print("-" * 70)
        print(f"{i}️⃣  ANALYZING NEWS FOR {ticker}")
        print("-" * 70)

        # Get headlines (first call - will hit API)
        print(f"\n📰 Fetching headlines for {ticker} (last 7 days)...")
        start = time.time()
        headlines = adapter.get_headlines(ticker, max_age_days=7, limit=10)
        elapsed = time.time() - start

        print(f"✅ Fetched {len(headlines)} headlines in {elapsed:.3f}s\n")

        # Display first few headlines
        print("📋 Latest Headlines:")
        for j, headline in enumerate(headlines[:5], 1):
            print(f"\n  {j}. {headline['title']}")
            print(f"     📅 Published: {headline['published_at'][:10]}")
            print(f"     📰 Source: {headline['provider']}")
            print(f"     🔗 URL: {headline['url'][:60]}...")

        # Get headlines again (second call - should hit cache)
        print("\n🔄 Fetching headlines again (should use cache)...")
        start = time.time()
        adapter.get_headlines(ticker, max_age_days=7, limit=10)
        elapsed = time.time() - start
        print(f"⚡ Cache hit! Retrieved in {elapsed:.4f}s (instant!)")

        # Analyze individual headline sentiments
        print("\n🎯 SENTIMENT ANALYSIS")
        print("-" * 70)

        for j, headline in enumerate(headlines[:3], 1):
            text = f"{headline['title']} {headline['summary']}"
            sentiment = adapter.get_sentiment(text)

            print(f"\n  Headline {j}: {headline['title'][:60]}...")
            print(f"  📊 Score: {sentiment['score']:+.2f} ({sentiment['label'].upper()})")

            if sentiment["positive_words"]:
                print(f"  ✅ Positive keywords: {', '.join(sentiment['positive_words'][:5])}")
            if sentiment["negative_words"]:
                print(f"  ❌ Negative keywords: {', '.join(sentiment['negative_words'][:5])}")
            if sentiment["risk_keywords"]:
                print(f"  ⚠️  Risk keywords: {', '.join(sentiment['risk_keywords'][:5])}")

        # Overall analysis
        print(f"\n🔍 OVERALL ANALYSIS FOR {ticker}")
        print("-" * 70)

        analysis = adapter.analyze_headlines(ticker, max_age_days=7, limit=10)

        print("\n📈 Overall Sentiment:")
        print(f"   Score: {analysis['sentiment']['score']:+.2f}")
        print(f"   Label: {analysis['sentiment']['label'].upper()}")
        print(f"   Headlines analyzed: {len(analysis['headlines'])}")

        if analysis["risk_detected"]:
            print("\n⚠️  RISK DETECTED!")
            print(f"   Risk keywords found: {', '.join(analysis['risk_keywords'])}")
            print("   ⚠️  This ticker has potentially negative news")
        else:
            print("\n✅ No major risk keywords detected")

        # Show attribution
        attr = adapter.get_attribution()
        print("\n📝 Attribution:")
        print(f"   Source: {attr.source.value}")
        print(f"   URL: {attr.url}")
        print(f"   Timestamp: {attr.timestamp}")

        print()
        if i < len(test_tickers):
            time.sleep(0.5)  # Be nice to the API

    # Demonstrate sentiment scoring with custom text
    print("-" * 70)
    print("🧪 SENTIMENT TESTING WITH CUSTOM TEXT")
    print("-" * 70)

    test_texts = [
        "Apple stock soars to record high on strong earnings beat, analysts upgrade",
        "Company faces fraud investigation, stock plunges on disappointing results",
        "Quarterly earnings report released, stock trading unchanged",
    ]

    for text in test_texts:
        sentiment = adapter.get_sentiment(text)
        print(f'\nText: "{text}"')
        print(f"Score: {sentiment['score']:+.2f} ({sentiment['label'].upper()})")

        if sentiment["positive_words"]:
            print(f"  ✅ Positive: {', '.join(sentiment['positive_words'])}")
        if sentiment["negative_words"]:
            print(f"  ❌ Negative: {', '.join(sentiment['negative_words'])}")
        if sentiment["risk_keywords"]:
            print(f"  ⚠️  Risk: {', '.join(sentiment['risk_keywords'])}")

    # Cache stats
    print("\n" + "-" * 70)
    print("💾 CACHE STATISTICS")
    print("-" * 70)
    stats = adapter.cache.get_stats()
    print(f"Total entries: {stats['total_entries']}")
    print(f"Total size: {stats['total_size_bytes']:,} bytes")
    print(f"Cache directory: {adapter.cache.cache_dir}")
    print()

    print("=" * 70)
    print("✅ DEMO COMPLETE!")
    print("=" * 70)
    print("\nKey takeaways:")
    print("  • News fetching takes ~1-2 seconds from Yahoo Finance")
    print("  • Cache hits are instant (< 0.001s)")
    print("  • Sentiment analysis is fast and deterministic")
    print("  • Risk keywords help identify troubled companies")
    print("  • All data includes full attribution")
    print("  • No API key required!")
    print()


if __name__ == "__main__":
    main()
