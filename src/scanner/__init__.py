"""Scanner module for candidate identification.

This module provides the core scanning infrastructure:
- Pipeline: Data flow for processing tickers
- Executor: Concurrent execution engine
- Engine: Main orchestration and persistence
"""

from src.scanner.engine import ScanConfig, ScanEngine, ScanResult
from src.scanner.executor import ConcurrentExecutor, ExecutorConfig, ExecutorStats
from src.scanner.pipeline import PipelineResult, PipelineStats, ScanPipeline

__all__ = [
    "ScanPipeline",
    "PipelineResult",
    "PipelineStats",
    "ConcurrentExecutor",
    "ExecutorConfig",
    "ExecutorStats",
    "ScanEngine",
    "ScanConfig",
    "ScanResult",
]
