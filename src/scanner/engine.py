"""Main scanning engine for identifying recovery candidates.

Orchestrates the complete scanning process:
1. Load ticker universe
2. Initialize strategies
3. Execute concurrent scanning
4. Persist results to database
5. Generate run metadata
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from src.datasources.prices import PriceAdapter
from src.ops.config import get_config
from src.ops.logging import get_logger, update_scan_status
from src.scanner.executor import ConcurrentExecutor, ExecutorConfig
from src.scanner.pipeline import ScanPipeline
from src.storage.database import SessionLocal
from src.storage.models import Candidate, Feature, Run, Ticker
from src.strategies.base import StrategyProtocol
from src.strategies.registry import get_registry

logger = get_logger(__name__)


@dataclass
class ScanConfig:
    """Configuration for a scan run."""

    strategies: list[str] | None = None  # None = all enabled
    universe_size: int | None = None  # None = all from adapter
    min_score: float = 0.5
    max_workers: int = 10
    timeout_seconds: int = 30
    lookback_days: int = 20


@dataclass
class ScanResult:
    """Result from a scan run."""

    run_id: str
    run_date: date
    strategy: str
    status: str
    duration_seconds: float
    tickers_processed: int
    candidates_found: int
    errors: int


class ScanEngine:
    """Main scanning engine for candidate identification.

    Coordinates the complete scanning workflow:
    - Loads ticker universe
    - Executes strategies concurrently
    - Persists results to database
    - Tracks run metadata
    """

    def __init__(
        self,
        price_adapter: PriceAdapter | None = None,
        db_session: Session | None = None,
    ):
        """Initialize scan engine.

        Args:
            price_adapter: Price data adapter (creates default if None)
            db_session: Database session (creates new if None)
        """
        self.price_adapter = price_adapter or PriceAdapter()
        self.db_session = db_session
        self.config = get_config()
        self.registry = get_registry()
        self.logger = get_logger(__name__)

    def run_scan(
        self,
        scan_config: ScanConfig | None = None,
        asof: date | None = None,
        run_ids: list[str] | None = None,
    ) -> list[ScanResult]:
        """Execute scan for specified strategies.

        Args:
            scan_config: Scan configuration (uses defaults if None)
            asof: Date to scan (defaults to today)
            run_ids: Optional pre-generated run IDs to use (one per strategy)

        Returns:
            List of scan results (one per strategy)
        """
        config = scan_config or ScanConfig()
        asof = asof or date.today()

        # Load strategies
        strategies = self._load_strategies(config.strategies)

        if not strategies:
            self.logger.warning("No strategies to execute")
            return []

        # Load universe
        universe = self._load_universe(config.universe_size)

        self.logger.info(
            "Starting scan",
            extra={
                "date": asof.isoformat(),
                "strategies": [s.name for s in strategies],
                "universe_size": len(universe),
            },
        )

        # Execute each strategy
        results = []
        for idx, strategy in enumerate(strategies):
            # Use provided run_id or generate new one
            run_id = run_ids[idx] if run_ids and idx < len(run_ids) else None
            result = self._run_strategy(strategy, universe, asof, config, run_id)
            results.append(result)

        return results

    def _load_strategies(self, strategy_names: list[str] | None) -> list[StrategyProtocol]:
        """Load strategies from registry.

        Args:
            strategy_names: List of strategy names (None = all enabled)

        Returns:
            List of strategy instances
        """
        # Discover and register strategies
        self.registry.discover_and_register()

        if strategy_names:
            # Load specific strategies
            strategies = []
            for name in strategy_names:
                try:
                    strategy = self.registry.get(name)
                    strategies.append(strategy)
                except Exception as e:
                    self.logger.error(
                        "Failed to load strategy",
                        extra={"strategy": name, "error": str(e)},
                    )
            return strategies
        else:
            # Load all enabled strategies (type-safe via overload)
            return self.registry.list_strategies(enabled_only=True)

    def _load_universe(self, max_size: int | None) -> list[str]:
        """Load ticker universe.

        Args:
            max_size: Maximum number of tickers (None = all)

        Returns:
            List of ticker symbols
        """
        universe = self.price_adapter.get_universe()

        if max_size and max_size < len(universe):
            universe = universe[:max_size]

        self.logger.info(
            "Loaded universe",
            extra={"total_tickers": len(universe)},
        )

        return universe

    def _run_strategy(
        self,
        strategy: StrategyProtocol,
        universe: list[str],
        asof: date,
        config: ScanConfig,
        run_id: str | None = None,
    ) -> ScanResult:
        """Execute a single strategy on the universe.

        Args:
            strategy: Strategy to execute
            universe: List of tickers
            asof: Scan date
            config: Scan configuration
            run_id: Optional pre-generated run ID to use

        Returns:
            ScanResult with outcome
        """
        run_id = run_id or str(uuid.uuid4())
        start_time = datetime.now(UTC)

        # Bind run_id to structlog context for all logs in this scope
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(run_id=run_id)

        self.logger.info(
            "Starting strategy run",
            extra={
                "run_id": run_id,
                "strategy": strategy.name,
                "date": asof.isoformat(),
                "tickers": len(universe),
            },
        )

        try:
            # Create pipeline
            pipeline = ScanPipeline(
                strategy=strategy,
                price_adapter=self.price_adapter,
                min_score=config.min_score,
                lookback_days=config.lookback_days,
            )

            # Create executor
            executor_config = ExecutorConfig(
                max_workers=config.max_workers,
                timeout_seconds=config.timeout_seconds,
            )
            executor = ConcurrentExecutor(pipeline, executor_config)

            # Create progress callback to update database
            def update_progress(completed: int, total: int, ticker: str, result: Any) -> None:
                """Update Run.tickers_processed in database and log ticker details."""
                if self.db_session:
                    try:
                        run = (
                            self.db_session.query(Run)
                            .filter(Run.run_id == uuid.UUID(run_id))
                            .first()
                        )
                        if run:
                            run.tickers_processed = completed  # type: ignore[assignment]
                            self.db_session.commit()

                            # Log detailed ticker processing info with run_id for SSE streaming
                            # Extract data from features if available
                            price = None
                            sector = None
                            market_cap = None
                            drop_pct = None
                            rsi = None
                            skip_reason = None

                            if result.features:
                                price = result.features.get("price")
                                sector = result.features.get("sector")
                                market_cap = result.features.get("market_cap")
                                drop_pct = result.features.get("drop_pct")
                                rsi = result.features.get("rsi")
                                skip_reason = result.features.get("skip_reason")

                            if result.score is not None:
                                # Scored candidate - show all details
                                price_str = f"${price:.2f}" if price else "N/A"
                                sector_str = f" | {sector}" if sector else ""
                                drop_str = f" | Drop: {drop_pct:.1f}%" if drop_pct else ""
                                rsi_str = f" | RSI: {rsi:.1f}" if rsi else ""
                                msg = f"✅ {ticker}: {price_str} - Score {result.score:.2f}{sector_str}{drop_str}{rsi_str}"
                                self.logger.info(
                                    msg,
                                    run_id=run_id,
                                    ticker=ticker,
                                    price=price,
                                    score=result.score,
                                    sector=sector,
                                    market_cap=market_cap,
                                    drop_pct=drop_pct,
                                    rsi=rsi,
                                )
                            elif result.passed_filter:
                                price_str = f"${price:.2f}" if price else "N/A"
                                sector_str = f" | {sector}" if sector else ""
                                msg = f"📊 {ticker}: {price_str} - Passed filter{sector_str}"
                                self.logger.info(
                                    msg, run_id=run_id, ticker=ticker, price=price, sector=sector
                                )
                            elif result.error:
                                msg = f"⚠️ {ticker}: Error - {result.error}"
                                self.logger.warning(
                                    msg, run_id=run_id, ticker=ticker, error=result.error
                                )
                            else:
                                # Skipped - show price, sector, drop %, and reason
                                price_str = f"${price:.2f}" if price else "N/A"
                                sector_str = f" | {sector}" if sector else ""
                                drop_str = f" | {drop_pct:+.1f}%" if drop_pct is not None else ""
                                reason_str = f" ({skip_reason})" if skip_reason else ""
                                msg = f"⏭️ {ticker}: {price_str}{drop_str} - Skipped{reason_str}{sector_str}"
                                self.logger.info(
                                    msg,
                                    run_id=run_id,
                                    ticker=ticker,
                                    price=price,
                                    sector=sector,
                                    drop_pct=drop_pct,
                                    skip_reason=skip_reason,
                                )
                    except Exception as e:
                        self.logger.error(
                            "Failed to update progress",
                            extra={"run_id": run_id, "error": str(e)},
                        )

            # Execute scan with progress tracking
            results, exec_stats = executor.execute(
                universe, asof, progress_callback=update_progress
            )

            # Get candidates
            candidates = pipeline.get_candidates(results)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Persist results
            self._persist_results(
                run_id=run_id,
                run_date=asof,
                strategy=strategy,
                results=results,
                candidates=candidates,
                duration=duration,
                config=config,
            )

            self.logger.info(
                "Strategy run complete",
                extra={
                    "run_id": run_id,
                    "strategy": strategy.name,
                    "processed": exec_stats.processed,
                    "candidates": len(candidates),
                    "duration_sec": f"{duration:.2f}",
                },
            )

            # Update in-memory status to "completed"
            update_scan_status(run_id, "completed")

            return ScanResult(
                run_id=run_id,
                run_date=asof,
                strategy=strategy.name,
                status="completed",
                duration_seconds=duration,
                tickers_processed=exec_stats.processed,
                candidates_found=len(candidates),
                errors=exec_stats.failed,
            )

        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds()

            self.logger.error(
                "Strategy run failed",
                extra={
                    "run_id": run_id,
                    "strategy": strategy.name,
                    "error": str(e),
                },
                exc_info=True,
            )

            # Update in-memory status to "failed"
            update_scan_status(run_id, "failed")

            return ScanResult(
                run_id=run_id,
                run_date=asof,
                strategy=strategy.name,
                status="failed",
                duration_seconds=duration,
                tickers_processed=0,
                candidates_found=0,
                errors=1,
            )

    def _persist_results(
        self,
        run_id: str,
        run_date: date,
        strategy: StrategyProtocol,
        results: list[Any],
        candidates: list[dict[str, Any]],
        duration: float,
        config: ScanConfig,
    ) -> None:
        """Persist scan results to database.

        Overwrites existing run if one exists for the same date/strategy combination.

        Args:
            run_id: Unique run identifier
            run_date: Scan date
            strategy: Strategy instance
            results: Pipeline results
            candidates: Candidate dictionaries
            duration: Execution duration
            config: Scan configuration
        """
        # Use provided session or create new one
        session = self.db_session or SessionLocal()

        try:
            # Check if run already exists for this date/strategy
            existing_run = (
                session.query(Run)
                .filter(Run.run_date == run_date, Run.strategy == strategy.name)
                .first()
            )

            if existing_run:
                # Delete existing run (cascade will delete Features and Candidates)
                self.logger.info(
                    "Overwriting existing run",
                    extra={
                        "existing_run_id": str(existing_run.run_id),
                        "new_run_id": run_id,
                        "run_date": str(run_date),
                        "strategy": strategy.name,
                    },
                )
                session.delete(existing_run)
                session.flush()  # Ensure delete completes before insert

            # Create Run record
            run = Run(
                run_id=uuid.UUID(run_id),
                run_date=run_date,
                strategy=strategy.name,
                status="completed",
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                duration_seconds=int(duration),
                tickers_processed=len([r for r in results if not r.error]),
                candidates_found=len(candidates),
                config_snapshot={
                    "min_score": config.min_score,
                    "max_workers": config.max_workers,
                    "lookback_days": config.lookback_days,
                    "strategy_version": strategy.version,
                },
            )
            session.add(run)

            # Create Feature records
            for result in results:
                if result.features:
                    feature = Feature(
                        ticker_symbol=result.ticker,
                        run_id=uuid.UUID(run_id),
                        asof=run_date,
                        strategy=strategy.name,
                        feature_version="1.0.0",  # TODO: Get from strategy
                        features=result.features,
                        attribution={},  # TODO: Add attribution
                    )
                    session.add(feature)

            # Create Candidate records
            for candidate in candidates:
                ticker_symbol = candidate["ticker"]

                # Ensure ticker exists in database (get-or-create pattern)
                ticker_record = session.query(Ticker).filter(Ticker.symbol == ticker_symbol).first()
                if not ticker_record:
                    self.logger.info(
                        "Creating missing ticker record",
                        extra={"ticker": ticker_symbol, "run_id": run_id},
                    )
                    try:
                        # Fetch ticker info
                        ticker_info = self.price_adapter.get_ticker_info(ticker_symbol)
                        ticker_record = Ticker(
                            symbol=ticker_symbol,
                            name=ticker_info.get("name", ticker_symbol),
                            sector=ticker_info.get("sector", "Unknown"),
                            industry=ticker_info.get("industry", "Unknown"),
                            market_cap=ticker_info.get("market_cap", 0),
                            is_active=True,
                        )
                        session.add(ticker_record)
                        session.flush()  # Ensure ticker is created before candidate
                    except Exception as e:
                        # If we can't fetch ticker info, create with minimal data
                        self.logger.warning(
                            "Failed to fetch ticker info, using minimal data",
                            extra={"ticker": ticker_symbol, "error": str(e)},
                        )
                        ticker_record = Ticker(
                            symbol=ticker_symbol,
                            name=ticker_symbol,  # Use symbol as name
                            sector="Unknown",
                            industry="Unknown",
                            market_cap=0,
                            is_active=True,
                        )
                        session.add(ticker_record)
                        session.flush()

                candidate_record = Candidate(
                    ticker_symbol=ticker_symbol,
                    run_id=uuid.UUID(run_id),
                    asof=run_date,
                    strategy=strategy.name,
                    score=candidate["score"],
                    rationale={
                        "features": candidate["features"],
                        "processing_time_ms": candidate["processing_time_ms"],
                    },
                    attribution={},  # TODO: Add attribution
                )
                session.add(candidate_record)

            session.commit()

            self.logger.info(
                "Results persisted",
                extra={
                    "run_id": run_id,
                    "candidates": len(candidates),
                    "features": len([r for r in results if r.features]),
                },
            )

        except Exception as e:
            session.rollback()
            self.logger.error(
                "Failed to persist results",
                extra={"run_id": run_id, "error": str(e)},
                exc_info=True,
            )
            raise

        finally:
            # Only close if we created the session
            if not self.db_session:
                session.close()
