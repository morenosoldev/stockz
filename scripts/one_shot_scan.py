#!/usr/bin/env python3
"""One-shot scan script for manual testing.

Usage:
    python scripts/one_shot_scan.py [--date YYYY-MM-DD] [--strategy STRATEGY_NAME]
"""

import argparse
import sys
from datetime import date, datetime

# Add src to path
sys.path.insert(0, "/workspaces/stockz")

from src.ops.logging import get_logger
from src.scanner.engine import ScanConfig, ScanEngine

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Run a one-shot scan")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Scan date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--strategy",
        type=str,
        default="drop5",
        help="Strategy to run. Defaults to 'drop5'.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=10,
        help="Maximum concurrent workers. Defaults to 10.",
    )

    args = parser.parse_args()

    # Parse date
    if args.date:
        scan_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        scan_date = date.today()

    logger.info(
        "Starting one-shot scan",
        extra={
            "date": str(scan_date),
            "strategy": args.strategy,
            "max_workers": args.max_workers,
        },
    )

    # Create scan engine
    engine = ScanEngine()

    # Create scan config
    config = ScanConfig(
        strategy_names=[args.strategy],
        max_workers=args.max_workers,
        min_score=0.5,
        lookback_days=30,
        timeout_seconds=1200,
    )

    # Run scan
    results = engine.scan(asof=scan_date, config=config)

    # Print results
    for result in results:
        logger.info(
            "Scan result",
            extra={
                "run_id": result.run_id,
                "strategy": result.strategy,
                "status": result.status,
                "duration_seconds": result.duration_seconds,
                "tickers_processed": result.tickers_processed,
                "candidates_found": result.candidates_found,
                "errors": result.errors,
            },
        )
        print(f"\n{'=' * 80}")
        print(f"Run ID: {result.run_id}")
        print(f"Strategy: {result.strategy}")
        print(f"Date: {result.run_date}")
        print(f"Status: {result.status}")
        print(f"Duration: {result.duration_seconds}s")
        print(f"Tickers Processed: {result.tickers_processed}")
        print(f"Candidates Found: {result.candidates_found}")
        print(f"Errors: {result.errors}")
        print(f"{'=' * 80}\n")


if __name__ == "__main__":
    main()
