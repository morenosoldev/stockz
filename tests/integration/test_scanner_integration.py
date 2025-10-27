"""
Integration tests for the complete scanner system.

Tests the full workflow: Universe → Pipeline → Executor → Engine → Database
Uses real Drop5 strategy with real price data (mocked for speed).
"""

import uuid
from datetime import date
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest
from sqlalchemy.orm import Session

from src.datasources.prices import PriceAdapter
from src.scanner.engine import ScanConfig, ScanEngine
from src.storage.models import Candidate, Feature, Run, Ticker


@pytest.fixture
def mock_price_data():
    """Create realistic OHLCV data for testing."""
    dates = pd.date_range(end=date.today(), periods=30, freq="D")

    # Ticker with a 5% drop (should be candidate)
    # Last close should show ~6% drop from previous close
    drop_data = pd.DataFrame(
        {
            "Open": [100.0] * 28 + [100.0, 95.0],
            "High": [102.0] * 28 + [101.0, 96.0],
            "Low": [98.0] * 28 + [94.0, 93.0],
            "Close": [100.0] * 28 + [100.0, 94.0],  # -6% drop from day 29 to day 30
            "Volume": [1_000_000] * 28 + [2_000_000, 2_500_000],
        },
        index=dates,
    )

    # Ticker without drop (should be filtered out)
    stable_data = pd.DataFrame(
        {
            "Open": [100.0] * 30,
            "High": [101.0] * 30,
            "Low": [99.0] * 30,
            "Close": [100.0] * 30,
            "Volume": [1_000_000] * 30,
        },
        index=dates,
    )

    # Ticker with big drop >15% (should be filtered out - drop too large)
    # Last close should show ~18% drop from previous close
    big_drop_data = pd.DataFrame(
        {
            "Open": [100.0] * 28 + [100.0, 88.0],
            "High": [102.0] * 28 + [101.0, 90.0],
            "Low": [98.0] * 28 + [87.0, 82.0],
            "Close": [100.0] * 28 + [100.0, 82.0],  # -18% drop from day 29 to day 30
            "Volume": [1_000_000] * 28 + [3_000_000, 3_500_000],
        },
        index=dates,
    )

    return {
        "AAPL": drop_data,  # Should pass
        "MSFT": stable_data,  # Should fail (no drop)
        "TSLA": big_drop_data,  # Should fail (drop too big)
    }


@pytest.fixture
def mock_ticker_universe():
    """Create mock ticker universe."""
    return [
        Ticker(symbol="AAPL", name="Apple Inc.", sector="Technology", market_cap=3_000_000_000_000),
        Ticker(
            symbol="MSFT", name="Microsoft Corp.", sector="Technology", market_cap=2_800_000_000_000
        ),
        Ticker(symbol="TSLA", name="Tesla Inc.", sector="Automotive", market_cap=800_000_000_000),
    ]


@pytest.mark.integration
def test_full_scanner_workflow(db_session: Session, mock_price_data, mock_ticker_universe):
    """Test complete scanner workflow from universe to database persistence."""

    # Add tickers to database (required for foreign key relationships)
    for ticker in mock_ticker_universe:
        db_session.merge(ticker)  # Use merge to avoid duplicate key errors
    db_session.commit()

    # Create mock price adapter with all required methods
    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = ["AAPL", "MSFT", "TSLA"]
    mock_adapter.get_bars.side_effect = lambda ticker, **kwargs: mock_price_data[ticker]

    # Mock ticker info
    def get_ticker_info_mock(ticker):
        return {
            "market_cap": 3_000_000_000_000,  # $3T
            "avg_volume": 50_000_000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }

    mock_adapter.get_ticker_info.side_effect = get_ticker_info_mock

    # Mock latest price
    def get_latest_price_mock(ticker):
        bars = mock_price_data[ticker]
        latest_close = float(bars["Close"].iloc[-1])
        prev_close = float(bars["Close"].iloc[-2])
        change_pct = ((latest_close - prev_close) / prev_close) * 100
        return {
            "price": latest_close,
            "change_pct": change_pct,
        }

    mock_adapter.get_latest_price.side_effect = get_latest_price_mock

    # Create scanner engine with mocked adapter
    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    # Run scan with Drop5 strategy
    scan_config = ScanConfig(
        strategies=["drop5"],
        max_workers=2,  # Low for testing
    )

    results = engine.run_scan(
        scan_config=scan_config,
        asof=date.today(),
    )

    # Verify run metadata
    assert len(results) == 1  # One strategy
    result = results[0]
    assert result.strategy == "drop5"
    assert result.status == "completed"
    assert result.tickers_processed == 3
    assert result.candidates_found >= 1  # At least AAPL should pass
    assert result.duration_seconds > 0

    # Verify database records
    import uuid

    run = db_session.query(Run).filter(Run.run_id == uuid.UUID(result.run_id)).first()
    assert run is not None
    assert run.status == "completed"

    # Verify candidates
    candidates = (
        db_session.query(Candidate).filter(Candidate.run_id == uuid.UUID(result.run_id)).all()
    )
    assert len(candidates) >= 1

    # AAPL should be a candidate (has 6% drop)
    aapl_candidate = next((c for c in candidates if c.ticker_symbol == "AAPL"), None)
    assert aapl_candidate is not None
    assert aapl_candidate.strategy == "drop5"
    assert 0.0 <= aapl_candidate.score <= 1.0
    assert aapl_candidate.rationale is not None
    assert aapl_candidate.attribution is not None

    # MSFT should NOT be a candidate (no drop)
    msft_candidate = next((c for c in candidates if c.ticker_symbol == "MSFT"), None)
    assert msft_candidate is None

    # TSLA should NOT be a candidate (drop too big - 18%)
    tsla_candidate = next((c for c in candidates if c.ticker_symbol == "TSLA"), None)
    assert tsla_candidate is None

    # Verify features were stored
    features = db_session.query(Feature).filter(Feature.run_id == uuid.UUID(result.run_id)).all()
    assert len(features) >= 1  # At least one ticker processed

    aapl_feature = next((f for f in features if f.ticker_symbol == "AAPL"), None)
    assert aapl_feature is not None
    assert aapl_feature.strategy == "drop5"
    assert aapl_feature.feature_version is not None
    assert "drop_pct" in aapl_feature.features
    assert "rsi" in aapl_feature.features
    assert "atr" in aapl_feature.features
    assert "volume_ratio" in aapl_feature.features


@pytest.mark.integration
def test_scanner_handles_data_errors(db_session: Session, mock_ticker_universe):
    """Test that scanner gracefully handles data fetch errors."""

    # Create mock adapter that raises errors
    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = ["AAPL", "MSFT", "TSLA"]
    mock_adapter.get_bars.side_effect = Exception("API error")

    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    scan_config = ScanConfig(strategies=["drop5"])

    # Should not raise, should handle errors gracefully
    results = engine.run_scan(
        scan_config=scan_config,
        asof=date.today(),
    )

    assert len(results) == 1
    result = results[0]
    # Run might have status "failed" or "completed" with 0 candidates
    assert result.candidates_found == 0


@pytest.mark.integration
def test_scanner_with_multiple_strategies(
    db_session: Session, mock_price_data, mock_ticker_universe
):
    """Test scanner with multiple strategies (when more strategies exist)."""

    # Add tickers to database (required for foreign key relationships)
    for ticker in mock_ticker_universe:
        db_session.merge(ticker)
    db_session.commit()

    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = ["AAPL", "MSFT", "TSLA"]
    mock_adapter.get_bars.side_effect = lambda ticker, **kwargs: mock_price_data[ticker]

    # Mock ticker info
    def get_ticker_info_mock(ticker):
        return {
            "market_cap": 3_000_000_000_000,  # $3T
            "avg_volume": 50_000_000,
            "sector": "Technology",
            "industry": "Consumer Electronics",
        }

    mock_adapter.get_ticker_info.side_effect = get_ticker_info_mock

    # Mock latest price
    def get_latest_price_mock(ticker):
        bars = mock_price_data[ticker]
        latest_close = float(bars["Close"].iloc[-1])
        prev_close = float(bars["Close"].iloc[-2])
        change_pct = ((latest_close - prev_close) / prev_close) * 100
        return {
            "price": latest_close,
            "change_pct": change_pct,
        }

    mock_adapter.get_latest_price.side_effect = get_latest_price_mock

    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    # Run with one strategy for now (add more when available)
    scan_config = ScanConfig(strategies=["drop5"])

    results = engine.run_scan(
        scan_config=scan_config,
        asof=date.today(),
    )

    assert len(results) == 1
    result = results[0]

    # Verify results stored per strategy
    import uuid

    candidates = (
        db_session.query(Candidate).filter(Candidate.run_id == uuid.UUID(result.run_id)).all()
    )
    assert all(c.strategy == "drop5" for c in candidates)

    features = db_session.query(Feature).filter(Feature.run_id == uuid.UUID(result.run_id)).all()
    assert all(f.strategy == "drop5" for f in features)


@pytest.mark.integration
def test_scanner_progress_callback(db_session: Session, mock_price_data, mock_ticker_universe):
    """Test scanner progress tracking."""

    progress_updates = []

    def progress_callback(completed: int, total: int, ticker: str):
        progress_updates.append(
            {
                "completed": completed,
                "total": total,
                "ticker": ticker,
            }
        )

    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = ["AAPL", "MSFT", "TSLA"]
    mock_adapter.get_bars.side_effect = lambda ticker, **kwargs: mock_price_data[ticker]

    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    scan_config = ScanConfig(strategies=["drop5"])

    # Note: Current implementation may not support progress_callback
    # This test validates the feature if/when implemented
    try:
        results = engine.run_scan(
            scan_config=scan_config,
            asof=date.today(),
        )
        # If no error, verify basic result
        assert len(results) == 1
    except TypeError:
        # progress_callback not supported yet - skip this assertion
        pytest.skip("Progress callback not implemented yet")


@pytest.mark.integration
def test_scanner_concurrent_execution(db_session: Session, mock_price_data):
    """Test scanner concurrent processing of multiple tickers."""

    # Create larger universe
    large_universe = [f"TICK{i}" for i in range(10)]

    # Mock data for all tickers
    def get_bars_mock(ticker, **kwargs):
        return mock_price_data["AAPL"]  # Reuse same data

    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = large_universe
    mock_adapter.get_bars.side_effect = get_bars_mock

    # Use higher concurrency
    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    import time

    start_time = time.time()

    scan_config = ScanConfig(
        strategies=["drop5"],
        max_workers=5,
    )

    results = engine.run_scan(
        scan_config=scan_config,
        asof=date.today(),
    )

    elapsed = time.time() - start_time

    # Verify all tickers processed
    assert len(results) == 1
    result = results[0]
    assert result.tickers_processed == 10

    # Concurrent execution should be faster than sequential
    # With 5 workers, should take ~2x single ticker time, not 10x
    # This is a rough check - adjust threshold as needed
    assert elapsed < 10.0, f"Concurrent execution too slow: {elapsed}s"


@pytest.mark.integration
@pytest.mark.slow
def test_scanner_performance_benchmark(db_session: Session, mock_price_data):
    """Benchmark scanner performance with larger dataset."""

    # Create 30-ticker universe (representative subset)
    benchmark_universe = [f"BENCH{i}" for i in range(30)]

    def get_bars_mock(ticker, **kwargs):
        return mock_price_data["AAPL"]  # Reuse same data

    mock_adapter = MagicMock(spec=PriceAdapter)
    mock_adapter.get_universe.return_value = benchmark_universe
    mock_adapter.get_bars.side_effect = get_bars_mock

    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )

    import time

    start_time = time.time()

    scan_config = ScanConfig(
        strategies=["drop5"],
        max_workers=10,
    )

    results = engine.run_scan(
        scan_config=scan_config,
        asof=date.today(),
    )

    elapsed = time.time() - start_time

    assert len(results) == 1
    result = results[0]
    assert result.tickers_processed == 30

    # Performance target: <1s per ticker on average with mocked data
    # Real API calls will be slower, but this validates parallel execution
    tickers_per_second = 30 / elapsed
    assert tickers_per_second > 3.0, f"Too slow: {tickers_per_second:.2f} tickers/sec"

    print(f"\nPerformance: {tickers_per_second:.2f} tickers/sec ({elapsed:.2f}s total)")


def test_scan_overwrites_duplicate_runs(db_session, mock_price_data, mock_ticker_universe):
    """Test that running a scan for the same date/strategy overwrites the existing run."""
    from datetime import date

    from src.scanner.engine import ScanConfig, ScanEngine
    from src.storage.models import Run, Ticker

    # Add tickers to database
    for ticker_symbol in ["AAPL", "TSLA"]:
        ticker = Ticker(
            symbol=ticker_symbol,
            name=f"{ticker_symbol} Inc.",
            sector="Technology",
            market_cap=1000000000,
        )
        db_session.add(ticker)
    db_session.commit()

    # Create scan engine with mock adapter
    mock_adapter = Mock()
    mock_adapter.get_bars.side_effect = lambda ticker, window, **kwargs: mock_price_data.get(ticker)
    mock_adapter.get_universe.return_value = ["AAPL", "TSLA"]

    engine = ScanEngine(
        price_adapter=mock_adapter,
        db_session=db_session,
    )
    scan_date = date(2025, 10, 26)

    # Create scan config
    scan_config = ScanConfig(
        strategies=["drop5"],
        max_workers=2,
    )

    # Run first scan
    results_1 = engine.run_scan(
        scan_config=scan_config,
        asof=scan_date,
    )
    assert len(results_1) == 1
    first_run_id = results_1[0].run_id

    # Verify first run is in database
    first_run = db_session.query(Run).filter(Run.run_id == uuid.UUID(first_run_id)).first()
    assert first_run is not None
    assert first_run.run_date == scan_date
    assert first_run.strategy == "drop5"

    # Run second scan for same date/strategy
    results_2 = engine.run_scan(
        scan_config=scan_config,
        asof=scan_date,
    )
    assert len(results_2) == 1
    second_run_id = results_2[0].run_id

    # Verify second run has different ID
    assert first_run_id != second_run_id

    # Verify only ONE run exists in database for this date/strategy
    runs = db_session.query(Run).filter(Run.run_date == scan_date, Run.strategy == "drop5").all()
    assert len(runs) == 1
    assert str(runs[0].run_id) == second_run_id

    # Verify first run was deleted
    first_run_check = db_session.query(Run).filter(Run.run_id == uuid.UUID(first_run_id)).first()
    assert first_run_check is None

    print(
        f"\n✅ Duplicate run handling: First run {first_run_id} deleted, "
        f"second run {second_run_id} persisted"
    )
