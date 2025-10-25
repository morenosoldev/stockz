#!/usr/bin/env python3
"""
Configuration verification script.

Verifies that the configuration is valid and prints the loaded config.
Useful for debugging configuration issues.

Usage:
    python scripts/verify_config.py
    python scripts/verify_config.py --config config/config.yaml
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ops.config import get_config, verify_config


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verify Recover-Bot configuration")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to config.yaml file (default: config/config.yaml)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output configuration as JSON",
    )
    args = parser.parse_args()

    try:
        # Load config
        print("🔍 Loading configuration...")
        config = get_config(args.config)

        # Verify config
        print("✅ Verifying configuration...")
        verify_config()

        print("\n✅ Configuration is valid!\n")

        # Print config
        if args.json:
            print(json.dumps(config.to_dict(), indent=2))
        else:
            print("=" * 80)
            print("CONFIGURATION SUMMARY")
            print("=" * 80)

            print("\n[Application]")
            print(f"  Name: {config.app.name}")
            print(f"  Version: {config.app.version}")
            print(f"  Environment: {config.app.env}")
            print(f"  Debug: {config.app.debug}")
            print(f"  Log Level: {config.app.log_level}")

            print("\n[Database]")
            print(f"  URL: {config.database.url}")
            print(f"  Pool Size: {config.database.pool_size}")
            print(f"  Max Overflow: {config.database.max_overflow}")

            print("\n[Scheduler]")
            print(f"  Enabled: {config.scheduler.enabled}")
            print(f"  Schedule: {config.scheduler.cron_schedule}")
            print(f"  Timezone: {config.scheduler.timezone}")

            print("\n[Scanner]")
            print(f"  Universe Size: {config.scanner.universe_size}")
            print(f"  Concurrency: {config.scanner.concurrency}")
            print(f"  Timeout: {config.scanner.timeout}s")
            print(f"  Cache TTL: {config.scanner.cache_ttl_seconds}s")

            print("\n[Data Sources]")
            print(f"  Price Provider: {config.datasources.price_provider}")
            print(
                f"  Yahoo Finance Key: {'Set' if config.datasources.yahoo_finance_api_key else 'Not set'}"
            )
            print(
                f"  Alpha Vantage Key: {'Set' if config.datasources.alpha_vantage_api_key else 'Not set'}"
            )
            print(f"  News API Key: {'Set' if config.datasources.news_api_key else 'Not set'}")

            print("\n[Strategies]")
            print(f"  Enabled: {', '.join(config.strategies.enabled_strategies)}")
            print(f"  Min Score Threshold: {config.strategies.min_score_threshold}")

            print("\n[Features]")
            print(f"  Version: {config.features.version}")
            print(f"  ATR Window: {config.features.atr_window}")
            print(f"  RSI Window: {config.features.rsi_window}")
            print(f"  SMA Window: {config.features.sma_window}")
            print(f"  Volume Window: {config.features.volume_window}")

            print("\n[Evaluation]")
            print(f"  Recovery Window: {config.evaluation.recovery_window_days} days")
            print(f"  Recovery Threshold: {config.evaluation.recovery_threshold_pct}%")

            print("\n[API]")
            print(f"  Host: {config.api.host}")
            print(f"  Port: {config.api.port}")
            print(f"  Docs Enabled: {config.api.docs_enabled}")
            print(f"  CORS Origins: {len(config.api.cors_origins)} configured")

            print("\n" + "=" * 80)

        return 0

    except Exception as e:
        print("\n❌ Configuration verification failed!")
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
