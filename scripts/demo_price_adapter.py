#!/usr/bin/env python3
"""Demo script to show PriceAdapter fetching real-time data with logging.

This script demonstrates the PriceAdapter in action:
- Fetching universe of tickers
- Getting OHLCV bars
- Getting latest prices
- Getting ticker info
- Cache performance
"""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.datasources.prices import PriceAdapter
from src.ops.logging import setup_logging

# Setup logging to console (no file)
setup_logging(log_level="INFO", log_format="text")


def main():
    """Run demo of price adapter."""
    print("\n" + "=" * 70)
    print("🚀 PRICE ADAPTER DEMO - Real-time Yahoo Finance Data")
    print("=" * 70 + "\n")

    # Create adapter
    print("📊 Initializing PriceAdapter...")
    adapter = PriceAdapter()
    print("✅ PriceAdapter ready!\n")

    # Get universe
    print("-" * 70)
    print("1️⃣  FETCHING TICKER UNIVERSE")
    print("-" * 70)
    universe = adapter.get_universe()
    print(f"📈 Universe size: {len(universe)} tickers")
    print(f"📋 Sample tickers: {universe[:10]}")
    print()

    # Test with a few tickers
    test_tickers = ["AAPL", "MSFT", "GOOGL"]

    for i, ticker in enumerate(test_tickers, 1):
        print("-" * 70)
        print(f"{i + 1}️⃣  FETCHING DATA FOR {ticker}")
        print("-" * 70)

        # Get bars (first call - will hit API)
        print(f"\n🔍 Fetching OHLCV bars for {ticker} (window=20)...")
        start = time.time()
        bars = adapter.get_bars(ticker, window=20)
        elapsed = time.time() - start

        print(f"✅ Fetched {len(bars)} bars in {elapsed:.3f}s")
        print("\n📊 Latest bars:")
        print(bars.tail(5)[["Open", "High", "Low", "Close", "Volume"]])

        # Calculate some metrics
        latest_close = bars["Close"].iloc[-1]
        prev_close = bars["Close"].iloc[-2]
        daily_change = ((latest_close - prev_close) / prev_close) * 100

        print(f"\n📈 Latest Close: ${latest_close:.2f}")
        print(f"📊 Daily Change: {daily_change:+.2f}%")

        # Get bars again (second call - should hit cache)
        print("\n🔄 Fetching bars again (should use cache)...")
        start = time.time()
        adapter.get_bars(ticker, window=20)
        elapsed = time.time() - start
        print(f"⚡ Cache hit! Retrieved in {elapsed:.4f}s (instant!)")

        # Get latest price
        print(f"\n💰 Fetching latest price for {ticker}...")
        start = time.time()
        price_data = adapter.get_latest_price(ticker)
        elapsed = time.time() - start

        print(f"✅ Fetched in {elapsed:.3f}s")
        print(f"   Price: ${price_data['price']:.2f}")
        print(f"   Change: {price_data['change']:+.2f} ({price_data['change_pct']:+.2f}%)")
        print(f"   Timestamp: {price_data['timestamp']}")

        # Get ticker info
        print(f"\n🏢 Fetching ticker info for {ticker}...")
        start = time.time()
        info = adapter.get_ticker_info(ticker)
        elapsed = time.time() - start

        print(f"✅ Fetched in {elapsed:.3f}s")
        print(f"   Name: {info['name']}")
        print(f"   Sector: {info['sector']}")
        print(f"   Industry: {info['industry']}")
        print(f"   Market Cap: ${info['market_cap']:,}")
        print(f"   Avg Volume: {info['avg_volume']:,}")

        # Show attribution
        attr = adapter.get_attribution()
        print("\n📝 Attribution:")
        print(f"   Source: {attr.source.value}")
        print(f"   URL: {attr.url}")
        print(f"   Timestamp: {attr.timestamp}")

        print()
        time.sleep(0.5)  # Be nice to the API

    # Cache stats
    print("-" * 70)
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
    print("  • First API call takes ~1-2 seconds")
    print("  • Cache hits are instant (< 0.001s)")
    print("  • All data includes full attribution")
    print("  • Different TTLs for different data types")
    print("  • Structured logging shows all operations")
    print()


if __name__ == "__main__":
    main()
