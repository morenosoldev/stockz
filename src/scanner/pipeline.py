"""Scanning pipeline for processing tickers through strategies.

This module provides a data flow pipeline that processes tickers:
1. Fetch market data (prices, volume, indicators)
2. Apply strategy filters
3. Extract features
4. Calculate scores
5. Filter by score threshold
6. Persist candidates to database
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from src.datasources.prices import PriceAdapter
from src.features.technical import calculate_atr, calculate_rsi, calculate_sma
from src.features.volume import calculate_rvol
from src.ops.logging import get_logger
from src.strategies.base import StrategyProtocol

logger = get_logger(__name__)


@dataclass
class PipelineResult:
    """Result from processing a ticker through the pipeline."""

    ticker: str
    passed_filter: bool
    features: dict[str, Any] | None = None
    score: float | None = None
    error: str | None = None
    processing_time_ms: float = 0.0


@dataclass
class PipelineStats:
    """Statistics from processing a batch of tickers."""

    total_tickers: int
    passed_filter: int
    scored: int
    above_threshold: int
    errors: int
    avg_processing_time_ms: float
    total_processing_time_ms: float


class ScanPipeline:
    """Data pipeline for scanning tickers with a strategy.

    The pipeline processes tickers in stages:
    1. Fetch: Get price data and metadata
    2. Filter: Apply strategy pre-filters
    3. Compute: Calculate technical indicators
    4. Extract: Extract strategy features
    5. Score: Calculate recovery probability
    6. Threshold: Filter by minimum score
    """

    def __init__(
        self,
        strategy: StrategyProtocol,
        price_adapter: PriceAdapter | None = None,
        min_score: float = 0.5,
        lookback_days: int = 20,
    ):
        """Initialize scan pipeline.

        Args:
            strategy: Strategy to use for scanning
            price_adapter: Price data adapter (creates default if None)
            min_score: Minimum score threshold (0.0-1.0)
            lookback_days: Days of historical data to fetch
        """
        self.strategy = strategy
        self.price_adapter = price_adapter or PriceAdapter()
        self.min_score = min_score
        self.lookback_days = lookback_days
        self.logger = get_logger(__name__)

    def process_ticker(self, ticker: str, asof: date | None = None) -> PipelineResult:
        """Process a single ticker through the pipeline.

        Args:
            ticker: Stock ticker symbol
            asof: Date to process (defaults to today)

        Returns:
            PipelineResult with processing outcome
        """
        start_time = datetime.now(UTC)

        try:
            # Stage 1: Fetch market data
            ticker_data = self._fetch_data(ticker, asof)

            # Stage 2: Apply pre-filter
            if not self.strategy.filters(ticker_data):
                elapsed = (datetime.now(UTC) - start_time).total_seconds() * 1000

                # Include basic info even for skipped tickers
                price_change = ticker_data.get("price_change_pct", 0)
                market_cap = ticker_data.get("market_cap", 0)
                avg_volume = ticker_data.get("avg_volume", 0)

                # Determine skip reason
                skip_reason = "did not pass filter"
                if market_cap < 1_000_000_000:
                    skip_reason = "market cap too small"
                elif avg_volume < 1_000_000:
                    skip_reason = "volume too low"
                elif not (-15 <= price_change <= -5):
                    if price_change > -5:
                        skip_reason = f"drop too small ({price_change:+.1f}%)"
                    else:
                        skip_reason = f"drop too large ({price_change:+.1f}%)"

                basic_features = {
                    "price": ticker_data.get("price"),
                    "sector": ticker_data.get("sector"),
                    "market_cap": market_cap,
                    "drop_pct": price_change,
                    "skip_reason": skip_reason,
                }
                return PipelineResult(
                    ticker=ticker,
                    passed_filter=False,
                    features=basic_features,
                    processing_time_ms=elapsed,
                )

            # Stage 3: Extract features
            features = self.strategy.features(ticker_data)

            # Stage 4: Calculate score
            score = self.strategy.score(features)

            elapsed = (datetime.now(UTC) - start_time).total_seconds() * 1000

            return PipelineResult(
                ticker=ticker,
                passed_filter=True,
                features=features,
                score=score,
                processing_time_ms=elapsed,
            )

        except Exception as e:
            elapsed = (datetime.now(UTC) - start_time).total_seconds() * 1000
            error_msg = f"{type(e).__name__}: {str(e)}"

            self.logger.error(
                "Pipeline error",
                extra={
                    "ticker": ticker,
                    "strategy": self.strategy.name,
                    "error": error_msg,
                },
            )

            return PipelineResult(
                ticker=ticker,
                passed_filter=False,
                error=error_msg,
                processing_time_ms=elapsed,
            )

    def _fetch_data(self, ticker: str, asof: date | None = None) -> dict[str, Any]:
        """Fetch market data for a ticker.

        Args:
            ticker: Stock ticker symbol
            asof: Date to fetch data for

        Returns:
            Dictionary with ticker data and indicators
        """
        # Fetch ticker metadata
        info = self.price_adapter.get_ticker_info(ticker)

        # Fetch OHLCV bars
        bars = self.price_adapter.get_bars(ticker, window=self.lookback_days)

        # Get latest price and change
        latest = self.price_adapter.get_latest_price(ticker)

        # Calculate technical indicators
        indicators = self._calculate_indicators(bars)

        # Build ticker data dictionary
        ticker_data = {
            "ticker": ticker,
            "price": latest.get("price", 0.0),  # Add current price
            "market_cap": info.get("market_cap", 0),
            "avg_volume": info.get("avg_volume", 0),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "price_change_pct": latest.get("change_pct", 0.0),
            "bars": self._bars_to_dict_list(bars),
            "indicators": indicators,
        }

        return ticker_data

    def _calculate_indicators(self, bars: Any) -> dict[str, Any]:
        """Calculate technical indicators from OHLCV bars.

        Args:
            bars: DataFrame with OHLCV data

        Returns:
            Dictionary of indicator values
        """
        if len(bars) < 2:
            return {}

        indicators = {}

        try:
            # RSI (14 period)
            rsi_series = calculate_rsi(bars, period=14, close_col="Close")
            if not rsi_series.empty:
                indicators["rsi"] = float(rsi_series.iloc[-1])

            # ATR (14 period)
            atr_series = calculate_atr(
                bars, period=14, high_col="High", low_col="Low", close_col="Close"
            )
            if not atr_series.empty:
                indicators["atr"] = float(atr_series.iloc[-1])

            # SMA (20 period)
            sma_series = calculate_sma(bars, period=20, price_col="Close")
            if not sma_series.empty:
                indicators["sma_20"] = float(sma_series.iloc[-1])

            # RVOL (20 period)
            rvol_series = calculate_rvol(bars, period=20, volume_col="Volume")
            if not rvol_series.empty:
                indicators["rvol"] = float(rvol_series.iloc[-1])

            # Volume average
            if "Volume" in bars.columns and len(bars) >= 20:
                indicators["volume_20d_avg"] = float(bars["Volume"].tail(20).mean())

        except Exception as e:
            self.logger.warning(
                "Indicator calculation failed",
                extra={"error": str(e)},
            )

        return indicators

    def _bars_to_dict_list(self, bars: Any) -> list[dict[str, Any]]:
        """Convert DataFrame bars to list of dictionaries.

        Args:
            bars: DataFrame with OHLCV data

        Returns:
            List of bar dictionaries
        """
        if bars.empty:
            return []

        # Convert to list of dicts with lowercase keys
        bars_list = []
        for idx, row in bars.iterrows():
            bar = {
                "date": idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx),
                "open": float(row.get("Open", 0)),
                "high": float(row.get("High", 0)),
                "low": float(row.get("Low", 0)),
                "close": float(row.get("Close", 0)),
                "volume": int(row.get("Volume", 0)),
            }
            bars_list.append(bar)

        return bars_list

    def process_batch(
        self, tickers: list[str], asof: date | None = None
    ) -> tuple[list[PipelineResult], PipelineStats]:
        """Process a batch of tickers through the pipeline.

        Args:
            tickers: List of ticker symbols
            asof: Date to process

        Returns:
            Tuple of (results list, batch statistics)
        """
        results = []
        total_time = 0.0

        for ticker in tickers:
            result = self.process_ticker(ticker, asof)
            results.append(result)
            total_time += result.processing_time_ms

        # Calculate statistics
        passed_filter = sum(1 for r in results if r.passed_filter)
        scored = sum(1 for r in results if r.score is not None)
        above_threshold = sum(
            1 for r in results if r.score is not None and r.score >= self.min_score
        )
        errors = sum(1 for r in results if r.error is not None)

        avg_time = total_time / len(results) if results else 0.0

        stats = PipelineStats(
            total_tickers=len(tickers),
            passed_filter=passed_filter,
            scored=scored,
            above_threshold=above_threshold,
            errors=errors,
            avg_processing_time_ms=avg_time,
            total_processing_time_ms=total_time,
        )

        self.logger.info(
            "Batch processing complete",
            extra={
                "strategy": self.strategy.name,
                "total": stats.total_tickers,
                "passed_filter": stats.passed_filter,
                "above_threshold": stats.above_threshold,
                "errors": stats.errors,
                "avg_time_ms": f"{stats.avg_processing_time_ms:.2f}",
            },
        )

        return results, stats

    def get_candidates(self, results: list[PipelineResult]) -> list[dict[str, Any]]:
        """Extract candidates from pipeline results.

        Filters results to only those with score >= min_score.

        Args:
            results: List of pipeline results

        Returns:
            List of candidate dictionaries
        """
        candidates = []

        for result in results:
            if result.score is not None and result.score >= self.min_score:
                candidate = {
                    "ticker": result.ticker,
                    "score": result.score,
                    "features": result.features,
                    "processing_time_ms": result.processing_time_ms,
                }
                candidates.append(candidate)

        return candidates
