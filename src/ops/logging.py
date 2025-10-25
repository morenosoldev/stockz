"""
Structured logging configuration for Recover-Bot.

Provides JSON-formatted structured logging with:
- Contextual information (request_id, user, run_id, etc.)
- Multiple output handlers (console, file, rotation)
- Log level configuration
- Exception logging with stack traces
- Integration with FastAPI and APScheduler
"""

import logging
import logging.handlers
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, Processor

from src.ops.config import get_config

# Global logger cache
_logger_cache: dict[str, structlog.BoundLogger] = {}


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

    # Configure structlog processors
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_log_level,
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
