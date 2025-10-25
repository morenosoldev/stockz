#!/usr/bin/env python3
"""
Example demonstrating structured logging usage.

Run with:
    python scripts/logging_example.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ops.logging import get_logger, init_logging, log_exception


def main():
    """Run logging examples."""
    # Initialize logging
    print("🔧 Initializing logging system...")
    init_logging(log_level="INFO", log_format="json")

    # Get a logger
    logger = get_logger(__name__)

    print("\n📝 Logging examples:\n")
    print("=" * 80)

    # Simple logging
    logger.info("Application started")
    logger.debug("This debug message won't appear (log level is INFO)")
    logger.warning("This is a warning")

    # Structured logging with context
    logger.info(
        "User logged in",
        user_id=123,
        username="john_doe",
        ip_address="192.168.1.100",
        session_id="abc-123-def-456",
    )

    # Logging with different levels
    logger.info("Processing data", records=1500, status="in_progress")
    logger.info("Data processing complete", records=1500, status="completed", duration_ms=2500)

    # Nested context
    logger.info(
        "Scan initiated",
        scan_id="scan_001",
        strategy="drop5",
        tickers_count=2000,
        parameters={"min_drop": 5.0, "max_days": 5},
    )

    # Error logging
    logger.error(
        "Database connection failed",
        host="localhost",
        port=5432,
        error_code="CONNECTION_TIMEOUT",
        retry_attempt=3,
    )

    # Example 8: Exception logging with context
    try:
        # Simulate an error
        _ = 10 / 0
    except ZeroDivisionError as e:
        log_exception(
            logger,
            e,
            "Mathematical operation failed",
            operation="division",
            numerator=10,
            denominator=0,
        )

    # Success message
    logger.info(
        "Logging examples completed",
        examples_shown=7,
        log_file="logs/recover-bot.log",
    )

    print("=" * 80)
    print("\n✅ Check logs/recover-bot.log for JSON formatted output!")
    print("\n💡 Each log entry includes:")
    print("   - timestamp (ISO 8601)")
    print("   - level (INFO, WARNING, ERROR, etc.)")
    print("   - event (log message)")
    print("   - Custom fields (user_id, scan_id, etc.)")
    print("\nExamples:")
    print(
        '   {"timestamp": "2025-10-24T12:00:00Z", "level": "INFO", "event": "User logged in", "user_id": 123, ...}'
    )


if __name__ == "__main__":
    main()
