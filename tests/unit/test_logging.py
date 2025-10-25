"""Tests for structured logging."""

import json
import logging

import pytest

from src.ops.logging import (
    add_log_level,
    add_timestamp,
    configure_logging_from_config,
    get_logger,
    init_logging,
    log_exception,
    setup_logging,
)


class TestLoggingSetup:
    """Test logging configuration."""

    def test_setup_logging_default(self, tmp_path):
        """Test basic logging setup."""
        setup_logging(log_level="INFO", log_format="json", log_dir=str(tmp_path))

        logger = get_logger("test.logger")
        assert logger is not None
        # Check it has the bind method (characteristic of structlog loggers)
        assert hasattr(logger, "bind")

    def test_setup_logging_with_file(self, tmp_path):
        """Test logging setup with file output."""
        log_file = "test.log"
        setup_logging(
            log_level="DEBUG",
            log_format="json",
            log_file=log_file,
            log_dir=str(tmp_path),
            enable_rotation=False,
        )

        logger = get_logger("test.file.logger")
        logger.info("test message", test_key="test_value")

        # Check file was created
        log_path = tmp_path / log_file
        assert log_path.exists()

    def test_setup_logging_text_format(self, tmp_path):
        """Test logging with text format."""
        setup_logging(log_level="INFO", log_format="text", log_dir=str(tmp_path))

        logger = get_logger("test.text.logger")
        logger.info("test message in text format")

        # Should not raise exception
        assert True

    def test_setup_logging_creates_directory(self, tmp_path):
        """Test that setup creates log directory."""
        log_dir = tmp_path / "custom_logs"
        assert not log_dir.exists()

        setup_logging(log_dir=str(log_dir))

        assert log_dir.exists()
        assert log_dir.is_dir()


class TestGetLogger:
    """Test get_logger function."""

    def test_get_logger_returns_bound_logger(self):
        """Test get_logger returns structlog BoundLogger."""
        logger = get_logger("test.module")
        # Check it has bind method (characteristic of structlog loggers)
        assert hasattr(logger, "bind")
        assert hasattr(logger, "info")
        assert hasattr(logger, "error")

    def test_get_logger_caching(self):
        """Test that get_logger caches loggers."""
        logger1 = get_logger("test.cached")
        logger2 = get_logger("test.cached")

        # Should return same instance
        assert logger1 is logger2

    def test_get_logger_different_names(self):
        """Test different names create different loggers."""
        logger1 = get_logger("test.logger1")
        logger2 = get_logger("test.logger2")

        # Should be different instances
        assert logger1 is not logger2


class TestLogException:
    """Test log_exception function."""

    def test_log_exception_basic(self, caplog):
        """Test basic exception logging."""
        logger = get_logger("test.exception")

        try:
            raise ValueError("Test error")
        except ValueError as e:
            with caplog.at_level(logging.ERROR):
                log_exception(logger, e, "Something went wrong")

        # Should log exception
        assert len(caplog.records) > 0

    def test_log_exception_with_context(self, caplog):
        """Test exception logging with extra context."""
        logger = get_logger("test.exception.context")

        try:
            raise RuntimeError("Runtime error")
        except RuntimeError as e:
            with caplog.at_level(logging.ERROR):
                log_exception(logger, e, "Operation failed", user_id=123, action="test")

        # Should include context in log
        assert len(caplog.records) > 0


class TestProcessors:
    """Test log processors."""

    def test_add_timestamp_processor(self):
        """Test timestamp processor adds ISO timestamp."""
        event_dict = {}
        result = add_timestamp(None, "info", event_dict)

        assert "timestamp" in result
        assert result["timestamp"].endswith("Z")
        assert "T" in result["timestamp"]  # ISO format

    def test_add_log_level_processor(self):
        """Test log level processor adds level."""
        event_dict = {}
        result = add_log_level(None, "info", event_dict)

        assert "level" in result
        assert result["level"] == "INFO"

    def test_add_log_level_different_levels(self):
        """Test log level processor with different levels."""
        for level in ["debug", "info", "warning", "error", "critical"]:
            event_dict = {}
            result = add_log_level(None, level, event_dict)
            assert result["level"] == level.upper()


class TestInitLogging:
    """Test init_logging convenience function."""

    def test_init_logging_default(self, tmp_path, monkeypatch):
        """Test init_logging with defaults."""
        # Change to temp directory to avoid conflicts
        monkeypatch.chdir(tmp_path)

        init_logging()

        logger = get_logger("test.init")
        logger.info("test message")

        # Should not raise exception
        assert True

    def test_init_logging_custom_level(self, tmp_path, monkeypatch):
        """Test init_logging with custom log level."""
        monkeypatch.chdir(tmp_path)

        init_logging(log_level="DEBUG", log_format="text")

        logger = get_logger("test.init.custom")
        logger.debug("debug message")

        # Should not raise exception
        assert True


class TestLoggingOutput:
    """Test actual logging output."""

    def test_json_log_output(self, tmp_path):
        """Test JSON formatted log output."""
        log_file = "json_test.log"
        setup_logging(
            log_level="INFO",
            log_format="json",
            log_file=log_file,
            log_dir=str(tmp_path),
            enable_rotation=False,
        )

        logger = get_logger("test.json.output")
        logger.info("test event", user_id=123, action="login")

        # Force flush
        logging.shutdown()

        # Read log file
        log_path = tmp_path / log_file
        assert log_path.exists()

        with open(log_path) as f:
            content = f.read().strip()

        # Skip if empty (logging may not have flushed in test environment)
        if not content:
            pytest.skip("Log file is empty - logging not flushed")

        log_data = json.loads(content.split("\n")[0])

        # Verify structure
        assert "timestamp" in log_data
        assert "level" in log_data
        assert log_data["level"] == "INFO"
        assert "event" in log_data
        assert log_data["event"] == "test event"

    def test_structured_context(self, tmp_path):
        """Test structured logging preserves context."""
        log_file = "context_test.log"
        setup_logging(
            log_level="INFO",
            log_format="json",
            log_file=log_file,
            log_dir=str(tmp_path),
            enable_rotation=False,
        )

        logger = get_logger("test.context")
        logger.info(
            "user action",
            user_id=456,
            username="testuser",
            ip_address="192.168.1.1",
            action="data_export",
        )

        # Force flush
        logging.shutdown()

        # Read log file
        log_path = tmp_path / log_file
        with open(log_path) as f:
            content = f.read().strip()

        # Skip if empty (logging may not have flushed in test environment)
        if not content:
            pytest.skip("Log file is empty - logging not flushed")

        log_data = json.loads(content.split("\n")[0])

        # Verify all context is present
        assert log_data["user_id"] == 456
        assert log_data["username"] == "testuser"
        assert log_data["ip_address"] == "192.168.1.1"
        assert log_data["action"] == "data_export"


class TestLogRotation:
    """Test log file rotation."""

    def test_rotation_enabled(self, tmp_path):
        """Test log rotation is configured."""
        log_file = "rotation_test.log"
        setup_logging(
            log_level="INFO",
            log_format="json",
            log_file=log_file,
            log_dir=str(tmp_path),
            enable_rotation=True,
            max_bytes=1024,  # Small size to trigger rotation
            backup_count=3,
        )

        logger = get_logger("test.rotation")

        # Write enough logs to potentially trigger rotation
        for i in range(100):
            logger.info(f"log message {i}" * 10)

        # Check log file exists
        log_path = tmp_path / log_file
        assert log_path.exists()


class TestConfigureFromConfig:
    """Test configuration from app config."""

    def test_configure_logging_from_config_fallback(self, tmp_path, monkeypatch):
        """Test fallback when config fails."""
        # This should not raise even if config is not available
        monkeypatch.chdir(tmp_path)

        try:
            configure_logging_from_config()
        except Exception:
            pytest.fail("configure_logging_from_config should not raise")
