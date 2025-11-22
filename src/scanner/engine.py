"""Main scanning engine for identifying recovery candidates.

Orchestrates the complete scanning process:
1. Load ticker universe
2. Initialize strategies
3. Execute concurrent scanning
4. Persist results to database
5. Generate run metadata
"""

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from src.datasources.prices import PriceAdapter
from src.ops.config import get_config
from src.ops.logging import get_logger, set_total_tickers, update_scan_status
from src.scanner.executor import ConcurrentExecutor, ExecutorConfig
from src.scanner.pipeline import ScanPipeline
from src.storage.database import SessionLocal
from src.storage.models import Candidate, Feature, Run, Ticker
from src.strategies.base import StrategyProtocol
from src.strategies.registry import get_registry

logger = get_logger(__name__)


# Class-level dictionary to track interrupt flags for each run_id
# Key: run_id (str), Value: threading.Event
_interrupt_flags: dict[str, threading.Event] = {}


def request_interrupt(run_id: str) -> bool:
    """Request interrupt for a running scan.

    Args:
        run_id: Run ID to interrupt

    Returns:
        True if interrupt flag was set, False if run_id not found
    """
    if run_id in _interrupt_flags:
        _interrupt_flags[run_id].set()
        logger.info("Interrupt requested", run_id=run_id)
        return True
    return False


def is_interrupted(run_id: str) -> bool:
    """Check if interrupt has been requested for a run.

    Args:
        run_id: Run ID to check

    Returns:
        True if interrupt requested, False otherwise
    """
    if run_id in _interrupt_flags:
        return _interrupt_flags[run_id].is_set()
    return False


def clear_interrupt(run_id: str) -> None:
    """Clear interrupt flag for a completed run.

    Args:
        run_id: Run ID to clear
    """
    if run_id in _interrupt_flags:
        del _interrupt_flags[run_id]
        logger.debug("Interrupt flag cleared", run_id=run_id)


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

        # Load default universe (S&P 500)
        default_universe = self._load_universe(config.universe_size)

        self.logger.info(
            "Starting scan",
            extra={
                "date": asof.isoformat(),
                "strategies": [s.name for s in strategies],
                "default_universe_size": len(default_universe),
            },
        )

        # Execute each strategy
        results = []
        for idx, strategy in enumerate(strategies):
            # Use provided run_id or generate new one
            run_id = run_ids[idx] if run_ids and idx < len(run_ids) else str(uuid.uuid4())

            # Bind run_id to structlog context early so get_universe() logs have run_id
            structlog.contextvars.clear_contextvars()
            structlog.contextvars.bind_contextvars(run_id=run_id)

            # Check if strategy provides its own universe (e.g., Reddit strategy)
            if hasattr(strategy, "provides_own_universe") and strategy.provides_own_universe:  # type: ignore[attr-defined]
                # Strategy discovers its own tickers (e.g., from Reddit, news, etc.)
                if hasattr(strategy, "get_universe"):
                    # Pass run_id if strategy supports cooperative interruption during universe discovery
                    try:  # type: ignore[attr-defined]
                        universe = strategy.get_universe(asof, run_id=run_id)  # type: ignore[arg-type]
                    except TypeError:
                        # Fallback to legacy signature without run_id
                        universe = strategy.get_universe(asof)  # type: ignore[attr-defined]
                    self.logger.info(
                        f"Strategy '{strategy.name}' using custom universe",
                        extra={
                            "strategy": strategy.name,
                            "custom_universe_size": len(universe),
                        },
                    )
                else:
                    self.logger.warning(
                        f"Strategy '{strategy.name}' has provides_own_universe=True but no get_universe() method",
                        extra={"strategy": strategy.name},
                    )
                    universe = default_universe
            else:
                # Use default S&P 500 universe
                universe = default_universe

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

        # Initialize interrupt flag for this run (if not already registered)
        if run_id not in _interrupt_flags:
            _interrupt_flags[run_id] = threading.Event()

        # run_id context already bound before get_universe() call
        # No need to bind again here

        # Set total tickers for progress tracking
        set_total_tickers(run_id, len(universe))

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

                                # Log detailed rationale for Reddit strategy
                                if strategy.name == "reddit" and result.features:
                                    llm_reasoning = result.features.get("llm_reasoning", [])
                                    catalysts = result.features.get("catalysts", [])
                                    risk_factors = result.features.get("risk_factors", [])
                                    mentions = result.features.get("mentions", 0)

                                    # Log main candidate line
                                    self.logger.info(
                                        msg,
                                        run_id=run_id,
                                        ticker=ticker,
                                        price=price,
                                        score=result.score,
                                        sector=sector,
                                        market_cap=market_cap,
                                        mentions=mentions,
                                    )

                                    # Log LLM reasoning details
                                    if llm_reasoning:
                                        self.logger.info(
                                            f"💭 {ticker} - LLM Analysis ({mentions} mentions):",
                                            run_id=run_id,
                                            ticker=ticker,
                                        )
                                        for idx, reasoning in enumerate(llm_reasoning, 1):
                                            self.logger.info(
                                                f"  📝 Analysis {idx}: {reasoning}",
                                                run_id=run_id,
                                                ticker=ticker,
                                                reasoning=reasoning,
                                            )

                                    # Log catalysts
                                    if catalysts:
                                        catalysts_str = ", ".join(catalysts)
                                        self.logger.info(
                                            f"  📈 Catalysts: {catalysts_str}",
                                            run_id=run_id,
                                            ticker=ticker,
                                            catalysts=catalysts,
                                        )

                                    # Log risk factors
                                    if risk_factors:
                                        risks_str = ", ".join(risk_factors)
                                        self.logger.info(
                                            f"  ⚠️ Risks: {risks_str}",
                                            run_id=run_id,
                                            ticker=ticker,
                                            risk_factors=risk_factors,
                                        )
                                else:
                                    # Non-Reddit strategy or no features
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
                universe, asof, progress_callback=update_progress, run_id=run_id
            )

            # Check if interrupted
            was_interrupted = is_interrupted(run_id)

            # Get candidates
            candidates = pipeline.get_candidates(results)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            # Persist results (including partial results if interrupted)
            self._persist_results(
                run_id=run_id,
                run_date=asof,
                strategy=strategy,
                results=results,
                candidates=candidates,
                duration=duration,
                config=config,
                interrupted=was_interrupted,
            )

            self.logger.info(
                "Strategy run complete" if not was_interrupted else "Strategy run stopped",
                extra={
                    "run_id": run_id,
                    "strategy": strategy.name,
                    "processed": exec_stats.processed,
                    "candidates": len(candidates),
                    "duration_sec": f"{duration:.2f}",
                    "interrupted": was_interrupted,
                },
            )

            # Update in-memory status
            final_status = "stopped" if was_interrupted else "completed"
            update_scan_status(run_id, final_status)

            # Clear interrupt flag
            clear_interrupt(run_id)

            return ScanResult(
                run_id=run_id,
                run_date=asof,
                strategy=strategy.name,
                status=final_status,
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

            # Clear interrupt flag
            clear_interrupt(run_id)

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
        interrupted: bool = False,
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
            interrupted: Whether the scan was interrupted by user
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
            run_status = "stopped" if interrupted else "completed"
            config_snapshot = {
                "min_score": config.min_score,
                "max_workers": config.max_workers,
                "lookback_days": config.lookback_days,
                "strategy_version": strategy.version,
            }

            # Add interrupted flag to config snapshot
            if interrupted:
                config_snapshot["interrupted"] = True
                # Find the last ticker processed
                if results:
                    last_ticker = results[-1].ticker if results else None
                    if last_ticker:
                        config_snapshot["stopped_at_ticker"] = last_ticker

            run = Run(
                run_id=uuid.UUID(run_id),
                run_date=run_date,
                strategy=strategy.name,
                status=run_status,
                started_at=datetime.now(UTC),
                completed_at=datetime.now(UTC),
                duration_seconds=int(duration),
                tickers_processed=len([r for r in results if not r.error]),
                candidates_found=len(candidates),
                config_snapshot=config_snapshot,
            )
            session.add(run)

            # Ensure all tickers exist FIRST (before creating Features/Candidates)
            all_tickers = set()
            for result in results:
                if result.features:
                    all_tickers.add(result.ticker)
            for candidate in candidates:
                all_tickers.add(candidate["ticker"])

            # Check if strategy provides own universe (e.g., Reddit) - skip ticker info fetching
            skip_ticker_info = (
                hasattr(strategy, "provides_own_universe") and strategy.provides_own_universe
            )  # type: ignore[attr-defined]

            for ticker_symbol in all_tickers:
                ticker_record = session.query(Ticker).filter(Ticker.symbol == ticker_symbol).first()
                if not ticker_record:
                    if skip_ticker_info:
                        # For custom universe strategies (Reddit, news, etc.), skip ticker info fetching
                        # These strategies don't need stock fundamentals - they analyze sentiment/events
                        self.logger.info(
                            "Creating ticker with minimal data (custom universe strategy)",
                            extra={
                                "ticker": ticker_symbol,
                                "strategy": strategy.name,
                                "run_id": run_id,
                            },
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
                    else:
                        # For traditional strategies (drop5, etc.), fetch ticker info
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
                            session.flush()  # Ensure ticker is created before features/candidates
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

                # Build comprehensive rationale
                rationale = {
                    "features": candidate["features"],
                    "processing_time_ms": candidate["processing_time_ms"],
                }

                # For Reddit strategy, include detailed LLM rationale
                if strategy.name == "reddit" and candidate.get("features"):
                    features = candidate["features"]
                    rationale["llm_analysis"] = {
                        "mentions": features.get("mentions", 0),
                        "reasoning": features.get("llm_reasoning", []),
                        "catalysts": features.get("catalysts", []),
                        "risk_factors": features.get("risk_factors", []),
                        "sentiment_details": features.get("sentiment_details", []),
                    }

                # Ticker now guaranteed to exist from ticker creation loop above
                candidate_record = Candidate(
                    ticker_symbol=ticker_symbol,
                    run_id=uuid.UUID(run_id),
                    asof=run_date,
                    strategy=strategy.name,
                    score=candidate["score"],
                    rationale=rationale,
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
