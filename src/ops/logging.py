"""
Structured logging utilities with real-time SSE streaming support.

Provides structured logging with JSON output, contextual fields,
and real-time streaming to Server-Sent Events (SSE) endpoints.
"""

import asyncio
import logging
import logging.handlers
import sys
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from structlog.types import EventDict, Processor

from src.ops.config import get_config

# Global logger cache to avoid repeated logger creation
_logger_cache: dict[str, structlog.BoundLogger] = {}

# Global async queues for SSE streaming (one queue per run_id)
# Queues are created by SSE endpoint when client connects (in async context)
_log_queues: dict[str, asyncio.Queue[dict[str, Any]]] = {}

# In-memory stats tracker for real-time updates (no database!)
_scan_stats: dict[str, dict[str, Any]] = defaultdict(
    lambda: {
        "tickers_processed": 0,
        "total_tickers": 0,
        "candidates_found": 0,
        "errors": 0,
        "start_time": None,
        "status": "running",
    }
)


def add_timestamp(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add ISO 8601 timestamp to log events."""
    event_dict["timestamp"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return event_dict


def add_log_level(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def add_logger_name(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Add logger name to event dict."""
    if hasattr(logger, "name"):
        event_dict["logger"] = logger.name
    return event_dict


def extract_run_id_to_record(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
    """Extract run_id and other fields from event_dict and attach to log record for StreamingLogHandler."""
    # Get the current log record being processed
    record = event_dict.get("_record")
    if record:
        # Attach run_id as record attribute so StreamingLogHandler can find it
        if "run_id" in event_dict:
            record.run_id = event_dict["run_id"]
        # Also check in 'extra' dict
        elif "extra" in event_dict and isinstance(event_dict["extra"], dict):
            if "run_id" in event_dict["extra"]:
                record.run_id = event_dict["extra"]["run_id"]

        # Also attach other streaming-relevant fields
        for field in ["ticker", "price", "strategy", "score", "event"]:
            if field in event_dict:
                setattr(record, field, event_dict[field])
            elif "extra" in event_dict and isinstance(event_dict["extra"], dict):
                if field in event_dict["extra"]:
                    setattr(record, field, event_dict["extra"][field])
    return event_dict


def setup_logging(
    log_level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
    log_dir: str = "logs",
    enable_rotation: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 7,
) -> None:
    """
    Configure structured logging for the application.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format ("json" or "text")
        log_file: Optional log file path
        log_dir: Directory for log files
        enable_rotation: Enable log file rotation
        max_bytes: Max bytes per log file (default: 10MB)
        backup_count: Number of backup files to keep (default: 7)
    """
    # Create logs directory if it doesn't exist
    log_path = Path(log_dir)
    log_path.mkdir(exist_ok=True)

    # Define SSE streaming processor
    def sse_stream_processor(logger: Any, method_name: str, event_dict: EventDict) -> EventDict:
        """Stream logs with run_id to SSE queues in REAL-TIME."""
        # Get run_id from contextvars first (set by scanner), then from event_dict
        run_id = structlog.contextvars.get_contextvars().get("run_id") or event_dict.get("run_id")

        if run_id:
            run_id_str = str(run_id)

            # Initialize stats if this is the first log
            if _scan_stats[run_id_str]["start_time"] is None:
                _scan_stats[run_id_str]["start_time"] = datetime.now(UTC)

            # Update stats based on log content
            message = event_dict.get("event", "")

            # Increment processed count when we process ANY ticker (scored, passed, or skipped)
            if "ticker" in event_dict:
                ticker = event_dict.get("ticker", "")
                # Only count if this is a ticker being processed (not just a status message)
                if ticker and any(
                    keyword in message for keyword in ["Score", "Passed", "Skipped", "Error"]
                ):
                    _scan_stats[run_id_str]["tickers_processed"] += 1

                # Increment candidates when we find a high score
                if "Score" in message and event_dict.get("score"):
                    _scan_stats[run_id_str]["candidates_found"] += 1

                # Increment errors
                if "Error" in message or "⚠️" in message:
                    _scan_stats[run_id_str]["errors"] += 1

            # Capture the beautifully formatted message from 'event' field
            log_entry = {
                "timestamp": event_dict.get("timestamp", datetime.now(UTC).isoformat()),
                "level": event_dict.get("level", method_name).lower(),
                "message": message,
                "event": message,
                "logger": event_dict.get("logger", ""),
            }

            # Add all extra fields
            for field in [
                "ticker",
                "price",
                "strategy",
                "score",
                "sector",
                "market_cap",
                "drop_pct",
                "rsi",
                "error",
                "skip_reason",
            ]:
                if field in event_dict:
                    log_entry[field] = event_dict[field]

            # Push to queue immediately (non-blocking) - ONLY if queue exists
            # Queue is created by SSE endpoint when client connects
            if run_id_str in _log_queues:
                queue = _log_queues[run_id_str]
                try:
                    queue.put_nowait(log_entry)
                except asyncio.QueueFull:
                    # Queue is full, drop oldest log (shouldn't happen with 1000 size)
                    try:
                        queue.get_nowait()
                        queue.put_nowait(log_entry)
                    except Exception:
                        pass  # If still fails, just skip this log
        return event_dict

    # Configure structlog processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_log_level,
        sse_stream_processor,  # Directly stream logs to SSE queue
        extract_run_id_to_record,  # For legacy StreamingLogHandler
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add appropriate renderer based on format
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Get root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    root_logger.addHandler(console_handler)

    # File handler with rotation
    if log_file:
        file_path = log_path / log_file
        file_handler: logging.Handler
        if enable_rotation:
            file_handler = logging.handlers.RotatingFileHandler(
                file_path,
                maxBytes=max_bytes,
                backupCount=backup_count,
            )
        else:
            file_handler = logging.FileHandler(file_path)

        file_handler.setLevel(getattr(logging, log_level.upper()))
        root_logger.addHandler(file_handler)

    # Set log levels for noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.INFO)


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Get or create a structured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        structlog.BoundLogger: Configured logger instance

    Example:
        >>> logger = get_logger(__name__)
        >>> logger.info("User logged in", user_id=123, ip="192.168.1.1")
        {"timestamp": "2025-10-24T12:00:00Z", "level": "INFO", "event": "User logged in", ...}
    """
    if name not in _logger_cache:
        _logger_cache[name] = structlog.get_logger(name)
    return _logger_cache[name]


def log_exception(
    logger: structlog.BoundLogger,
    exception: Exception,
    message: str = "Exception occurred",
    **context: Any,
) -> None:
    """
    Log an exception with full context and stack trace.

    Args:
        logger: Logger instance
        exception: Exception to log
        message: Log message
        **context: Additional context to include

    Example:
        >>> try:
        ...     risky_operation()
        ... except Exception as e:
        ...     log_exception(logger, e, "Operation failed", user_id=123)
    """
    logger.error(
        message,
        exc_info=exception,
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        **context,
    )


def configure_logging_from_config() -> None:
    """
    Configure logging from application config.

    Reads configuration from src.ops.config and sets up logging accordingly.
    """
    try:
        config = get_config()
        setup_logging(
            log_level=config.app.log_level,
            log_format=config.app.log_format,
            log_file="recover-bot.log" if config.app.structured_logging else None,
            enable_rotation=True,
        )
    except Exception as e:
        # Fallback to basic logging if config fails
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logging.error(f"Failed to configure logging from config: {e}")


# Convenience function for quick logger setup
def init_logging(log_level: str = "INFO", log_format: str = "json") -> None:
    """
    Initialize logging with sensible defaults.

    Args:
        log_level: Logging level (default: INFO)
        log_format: Output format (default: json)

    Example:
        >>> from src.ops.logging import init_logging, get_logger
        >>> init_logging()
        >>> logger = get_logger(__name__)
        >>> logger.info("Application started")
    """
    setup_logging(log_level=log_level, log_format=log_format, log_file="recover-bot.log")


# Auto-configure on module import if config is available
try:
    configure_logging_from_config()
except Exception:
    # Silently fail - user can call init_logging() or setup_logging() manually
    pass


# ============================================================================
# Log Streaming / Aggregator for SSE
# ============================================================================


async def stream_logs(run_id: str | UUID) -> AsyncIterator[dict[str, Any]]:
    """
    Stream logs for a specific run ID in REAL-TIME from async queue.

    Args:
        run_id: UUID of the scan run

    Yields:
        dict: Log entry with timestamp, level, message, etc.
    """
    run_id_str = str(run_id)

    # Create queue if it doesn't exist yet (SSE endpoint creates it here!)
    if run_id_str not in _log_queues:
        _log_queues[run_id_str] = asyncio.Queue(maxsize=1000)

    queue = _log_queues[run_id_str]

    try:
        while True:
            # Wait for next log entry (blocks until available)
            # Use timeout to periodically check if scan is still running
            try:
                log_entry = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield log_entry
            except TimeoutError:
                # No logs in last second, continue waiting
                continue

    except asyncio.CancelledError:
        # Client disconnected
        pass
    finally:
        # Cleanup queue when stream ends
        if run_id_str in _log_queues and queue.empty():
            del _log_queues[run_id_str]


def clear_logs(run_id: str | UUID) -> None:
    """Clear logs for a specific run to free memory."""
    run_id_str = str(run_id)
    if run_id_str in _log_queues:
        del _log_queues[run_id_str]
    if run_id_str in _scan_stats:
        del _scan_stats[run_id_str]


def get_scan_stats(run_id: str | UUID) -> dict[str, Any]:
    """
    Get real-time in-memory stats for a scan run.

    Args:
        run_id: UUID of the scan run

    Returns:
        dict with tickers_processed, total_tickers, candidates_found, errors, duration_seconds, status
    """
    run_id_str = str(run_id)
    stats = _scan_stats[run_id_str]

    # Calculate duration
    duration_seconds = 0
    if stats["start_time"]:
        duration_seconds = int((datetime.now(UTC) - stats["start_time"]).total_seconds())

    return {
        "tickers_processed": stats["tickers_processed"],
        "total_tickers": stats["total_tickers"],
        "candidates_found": stats["candidates_found"],
        "errors": stats["errors"],
        "duration_seconds": duration_seconds,
        "status": stats["status"],
    }


def update_scan_status(run_id: str | UUID, status: str) -> None:
    """Update the status of a scan run in memory."""
    run_id_str = str(run_id)
    _scan_stats[run_id_str]["status"] = status


def set_total_tickers(run_id: str | UUID, total: int) -> None:
    """Set the total number of tickers for a scan run."""
    run_id_str = str(run_id)
    _scan_stats[run_id_str]["total_tickers"] = total
