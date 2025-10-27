"""Concurrent execution engine for scanning multiple tickers.

Provides thread-pool based concurrent execution with:
- Rate limiting per data source
- Timeout handling
- Progress tracking
- Error recovery
"""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from typing import Any

from src.ops.logging import get_logger
from src.scanner.pipeline import PipelineResult, ScanPipeline

logger = get_logger(__name__)


@dataclass
class ExecutorConfig:
    """Configuration for concurrent executor."""

    max_workers: int = 10
    timeout_seconds: int = 30
    rate_limit_delay: float = 0.1  # Delay between requests in seconds
    batch_size: int = 50  # Process in batches for memory management


@dataclass
class ExecutorStats:
    """Statistics from concurrent execution."""

    total_tickers: int
    processed: int
    failed: int
    timed_out: int
    duration_seconds: float
    tickers_per_second: float


class ConcurrentExecutor:
    """Concurrent executor for processing tickers through pipeline.

    Uses ThreadPoolExecutor to process multiple tickers in parallel
    while respecting rate limits and timeouts.
    """

    def __init__(
        self,
        pipeline: ScanPipeline,
        config: ExecutorConfig | None = None,
    ):
        """Initialize concurrent executor.

        Args:
            pipeline: ScanPipeline instance
            config: Executor configuration (uses defaults if None)
        """
        self.pipeline = pipeline
        self.config = config or ExecutorConfig()
        self.logger = get_logger(__name__)

    def execute(
        self,
        tickers: list[str],
        asof: date | None = None,
        progress_callback: Callable[[int, int, str, Any], None] | None = None,
    ) -> tuple[list[PipelineResult], ExecutorStats]:
        """Execute pipeline on list of tickers concurrently.

        Args:
            tickers: List of ticker symbols to process
            asof: Date to process (defaults to today)
            progress_callback: Optional callback(completed, total, ticker, result)

        Returns:
            Tuple of (results list, execution statistics)
        """
        start_time = time.time()
        results: list[PipelineResult] = []
        failed = 0
        timed_out = 0

        self.logger.info(
            "Starting concurrent execution",
            extra={
                "total_tickers": len(tickers),
                "max_workers": self.config.max_workers,
                "batch_size": self.config.batch_size,
            },
        )

        # Process in batches for memory management
        for batch_start in range(0, len(tickers), self.config.batch_size):
            batch_end = min(batch_start + self.config.batch_size, len(tickers))
            batch = tickers[batch_start:batch_end]

            batch_results, batch_failed, batch_timed_out = self._process_batch(
                batch, asof, progress_callback, batch_start
            )

            results.extend(batch_results)
            failed += batch_failed
            timed_out += batch_timed_out

        duration = time.time() - start_time

        stats = ExecutorStats(
            total_tickers=len(tickers),
            processed=len(results),
            failed=failed,
            timed_out=timed_out,
            duration_seconds=duration,
            tickers_per_second=len(results) / duration if duration > 0 else 0,
        )

        self.logger.info(
            "Concurrent execution complete",
            extra={
                "total": stats.total_tickers,
                "processed": stats.processed,
                "failed": stats.failed,
                "timed_out": stats.timed_out,
                "duration_sec": f"{stats.duration_seconds:.2f}",
                "tickers_per_sec": f"{stats.tickers_per_second:.2f}",
            },
        )

        return results, stats

    def _process_batch(
        self,
        batch: list[str],
        asof: date | None,
        progress_callback: Callable[[int, int, str, Any], None] | None,
        offset: int,
    ) -> tuple[list[PipelineResult], int, int]:
        """Process a batch of tickers concurrently.

        Args:
            batch: Batch of ticker symbols
            asof: Date to process
            progress_callback: Progress callback(completed, total, ticker, result)
            offset: Offset for progress reporting

        Returns:
            Tuple of (results, failed_count, timeout_count)
        """
        results: list[PipelineResult] = []
        failed = 0
        timed_out = 0

        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            # Submit all tasks
            future_to_ticker = {
                executor.submit(self._process_with_delay, ticker, asof, i): ticker
                for i, ticker in enumerate(batch)
            }

            # Collect results as they complete
            for future in as_completed(
                future_to_ticker, timeout=self.config.timeout_seconds * len(batch)
            ):
                ticker = future_to_ticker[future]

                try:
                    result = future.result(timeout=self.config.timeout_seconds)
                    results.append(result)

                    # Report progress with ticker info
                    if progress_callback:
                        progress_callback(
                            offset + len(results), offset + len(batch), ticker, result
                        )

                except TimeoutError:
                    timed_out += 1
                    self.logger.warning(
                        "Ticker processing timed out",
                        extra={"ticker": ticker, "timeout": self.config.timeout_seconds},
                    )

                    # Add timeout result
                    results.append(
                        PipelineResult(
                            ticker=ticker,
                            passed_filter=False,
                            error="TimeoutError",
                        )
                    )

                except Exception as e:
                    failed += 1
                    self.logger.error(
                        "Ticker processing failed",
                        extra={"ticker": ticker, "error": str(e)},
                    )

                    # Add error result
                    results.append(
                        PipelineResult(
                            ticker=ticker,
                            passed_filter=False,
                            error=f"{type(e).__name__}: {str(e)}",
                        )
                    )

        return results, failed, timed_out

    def _process_with_delay(self, ticker: str, asof: date | None, index: int) -> PipelineResult:
        """Process ticker with rate limiting delay.

        Args:
            ticker: Ticker symbol
            asof: Date to process
            index: Index in batch (for delay calculation)

        Returns:
            PipelineResult
        """
        # Apply rate limiting delay (stagger requests)
        delay = index * self.config.rate_limit_delay
        if delay > 0:
            time.sleep(delay)

        return self.pipeline.process_ticker(ticker, asof)

    def execute_with_retry(
        self,
        tickers: list[str],
        asof: date | None = None,
        max_retries: int = 2,
        progress_callback: Callable[[int, int, str, Any], None] | None = None,
    ) -> tuple[list[PipelineResult], ExecutorStats]:
        """Execute with automatic retry for failed tickers.

        Args:
            tickers: List of ticker symbols
            asof: Date to process
            max_retries: Maximum retry attempts for failed tickers
            progress_callback: Progress callback(completed, total, ticker, result)

        Returns:
            Tuple of (results, stats)
        """
        all_results: dict[str, PipelineResult] = {}
        retry_tickers = tickers.copy()
        attempt = 0

        while retry_tickers and attempt <= max_retries:
            self.logger.info(
                "Execution attempt",
                extra={"attempt": attempt + 1, "tickers": len(retry_tickers)},
            )

            results, stats = self.execute(retry_tickers, asof, progress_callback)

            # Store results
            for result in results:
                all_results[result.ticker] = result

            # Identify tickers to retry (those with errors, not filters)
            if attempt < max_retries:
                retry_tickers = [r.ticker for r in results if r.error is not None]

                if retry_tickers:
                    self.logger.info(
                        "Retrying failed tickers",
                        extra={"count": len(retry_tickers), "attempt": attempt + 2},
                    )
            else:
                retry_tickers = []

            attempt += 1

        # Convert dict back to list
        final_results = list(all_results.values())

        # Calculate final stats
        final_stats = ExecutorStats(
            total_tickers=len(tickers),
            processed=len([r for r in final_results if r.error is None]),
            failed=len([r for r in final_results if r.error is not None]),
            timed_out=len([r for r in final_results if r.error == "TimeoutError"]),
            duration_seconds=stats.duration_seconds,
            tickers_per_second=(
                len(final_results) / stats.duration_seconds if stats.duration_seconds > 0 else 0
            ),
        )

        return final_results, final_stats
