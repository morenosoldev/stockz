"""Tests for scanner executor."""

import pytest

from src.scanner.executor import ConcurrentExecutor, ExecutorConfig
from src.scanner.pipeline import PipelineResult, ScanPipeline
from src.strategies.drop5.implementation import Drop5Strategy


class TestExecutorConfig:
    """Test ExecutorConfig dataclass."""

    def test_default_config(self):
        """Test default executor configuration."""
        config = ExecutorConfig()

        assert config.max_workers == 10
        assert config.timeout_seconds == 30
        assert config.rate_limit_delay == 0.1
        assert config.batch_size == 50

    def test_custom_config(self):
        """Test custom executor configuration."""
        config = ExecutorConfig(
            max_workers=5,
            timeout_seconds=60,
            rate_limit_delay=0.2,
            batch_size=100,
        )

        assert config.max_workers == 5
        assert config.timeout_seconds == 60
        assert config.rate_limit_delay == 0.2
        assert config.batch_size == 100


class TestConcurrentExecutor:
    """Test ConcurrentExecutor class."""

    def test_executor_initialization(self):
        """Test executor initializes correctly."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)
        executor = ConcurrentExecutor(pipeline)

        assert executor.pipeline == pipeline
        assert executor.config is not None
        assert isinstance(executor.config, ExecutorConfig)

    def test_executor_custom_config(self):
        """Test executor with custom configuration."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)
        config = ExecutorConfig(max_workers=5)
        executor = ConcurrentExecutor(pipeline, config)

        assert executor.config.max_workers == 5

    def test_execute_small_batch(self):
        """Test executing a small batch of tickers."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        config = ExecutorConfig(max_workers=2, batch_size=10)
        executor = ConcurrentExecutor(pipeline, config)

        tickers = ["AAPL", "MSFT", "GOOGL"]
        results, stats = executor.execute(tickers)

        assert len(results) == 3
        assert stats.total_tickers == 3
        assert stats.processed <= 3
        assert stats.duration_seconds > 0
        assert stats.tickers_per_second > 0

    def test_execute_with_progress_callback(self):
        """Test execution with progress callback."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        executor = ConcurrentExecutor(pipeline)

        progress_calls = []

        def progress_callback(completed, total, ticker, result):
            progress_calls.append((completed, total, ticker))

        tickers = ["AAPL", "MSFT"]
        results, stats = executor.execute(tickers, progress_callback=progress_callback)

        assert len(results) == 2
        # Progress callback should have been called
        assert len(progress_calls) > 0

    def test_execute_empty_list(self):
        """Test executing empty ticker list."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)
        executor = ConcurrentExecutor(pipeline)

        results, stats = executor.execute([])

        assert len(results) == 0
        assert stats.total_tickers == 0
        assert stats.processed == 0

    def test_execute_with_invalid_tickers(self):
        """Test execution handles invalid tickers gracefully."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)
        config = ExecutorConfig(max_workers=2, timeout_seconds=10)
        executor = ConcurrentExecutor(pipeline, config)

        tickers = ["AAPL", "INVALID_XYZ", "MSFT"]
        results, stats = executor.execute(tickers)

        assert len(results) == 3
        # Should have at least one error (INVALID_XYZ)
        errors = [r for r in results if r.error is not None]
        assert len(errors) >= 1

    def test_execute_with_retry(self):
        """Test execution with retry for failed tickers."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        config = ExecutorConfig(max_workers=2)
        executor = ConcurrentExecutor(pipeline, config)

        tickers = ["AAPL", "MSFT"]
        results, stats = executor.execute_with_retry(tickers, max_retries=1)

        assert len(results) == 2
        assert stats.total_tickers == 2

    def test_process_with_delay(self):
        """Test that rate limiting delay is applied."""
        import time

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        config = ExecutorConfig(rate_limit_delay=0.1)
        executor = ConcurrentExecutor(pipeline, config)

        start = time.time()
        result = executor._process_with_delay("AAPL", None, index=2)
        elapsed = time.time() - start

        assert isinstance(result, PipelineResult)
        # Should have delayed by 0.1 * 2 = 0.2 seconds
        assert elapsed >= 0.2

    def test_process_with_delay_first_item(self):
        """Test no delay for first item (index=0)."""
        import time

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        config = ExecutorConfig(rate_limit_delay=0.1)
        executor = ConcurrentExecutor(pipeline, config)

        start = time.time()
        result = executor._process_with_delay("AAPL", None, index=0)
        elapsed = time.time() - start

        assert isinstance(result, PipelineResult)
        # Should have minimal delay for first item
        assert elapsed < 0.1

    def test_batch_processing(self):
        """Test processing larger list in batches."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)
        config = ExecutorConfig(max_workers=3, batch_size=2)
        executor = ConcurrentExecutor(pipeline, config)

        # 5 tickers with batch_size=2 should create 3 batches
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META"]
        results, stats = executor.execute(tickers)

        assert len(results) == 5
        assert stats.total_tickers == 5


class TestExecutorStats:
    """Test ExecutorStats dataclass."""

    def test_stats_creation(self):
        """Test creating executor statistics."""
        from src.scanner.executor import ExecutorStats

        stats = ExecutorStats(
            total_tickers=100,
            processed=95,
            failed=3,
            timed_out=2,
            duration_seconds=120.5,
            tickers_per_second=0.79,
        )

        assert stats.total_tickers == 100
        assert stats.processed == 95
        assert stats.failed == 3
        assert stats.timed_out == 2
        assert stats.duration_seconds == 120.5
        assert stats.tickers_per_second == pytest.approx(0.79, abs=0.01)
