"""Tests for scanner pipeline."""

from src.datasources.prices import PriceAdapter
from src.scanner.pipeline import PipelineResult, ScanPipeline
from src.strategies.drop5.implementation import Drop5Strategy


class TestScanPipeline:
    """Test ScanPipeline class."""

    def test_pipeline_initialization(self):
        """Test pipeline initializes correctly."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        assert pipeline.strategy == strategy
        assert pipeline.price_adapter is not None
        assert pipeline.min_score == 0.5
        assert pipeline.lookback_days == 20

    def test_pipeline_custom_config(self):
        """Test pipeline with custom configuration."""
        strategy = Drop5Strategy()
        price_adapter = PriceAdapter()
        pipeline = ScanPipeline(
            strategy=strategy,
            price_adapter=price_adapter,
            min_score=0.7,
            lookback_days=30,
        )

        assert pipeline.min_score == 0.7
        assert pipeline.lookback_days == 30
        assert pipeline.price_adapter == price_adapter

    def test_process_ticker_real_data(self):
        """Test processing ticker with real market data."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)  # Low threshold for testing

        result = pipeline.process_ticker("AAPL")

        assert isinstance(result, PipelineResult)
        assert result.ticker == "AAPL"
        assert result.processing_time_ms > 0

        # Should have processed (passed or failed filter)
        assert result.passed_filter is not None

    def test_process_ticker_invalid(self):
        """Test processing invalid ticker."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        result = pipeline.process_ticker("INVALID_TICKER_XYZ")

        assert result.ticker == "INVALID_TICKER_XYZ"
        assert result.error is not None
        assert result.passed_filter is False

    def test_process_batch(self):
        """Test batch processing with real tickers."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.0)

        tickers = ["AAPL", "MSFT", "GOOGL"]
        results, stats = pipeline.process_batch(tickers)

        assert len(results) == 3
        assert stats.total_tickers == 3
        assert stats.avg_processing_time_ms > 0
        assert stats.total_processing_time_ms > 0

    def test_process_batch_empty(self):
        """Test batch processing with empty list."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        results, stats = pipeline.process_batch([])

        assert len(results) == 0
        assert stats.total_tickers == 0
        assert stats.passed_filter == 0
        assert stats.scored == 0

    def test_get_candidates_filtering(self):
        """Test candidate extraction with score filtering."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.6)

        # Create mock results
        results = [
            PipelineResult(
                ticker="AAPL",
                passed_filter=True,
                score=0.8,
                features={"drop_pct": -7.0},
                processing_time_ms=100.0,
            ),
            PipelineResult(
                ticker="MSFT",
                passed_filter=True,
                score=0.4,  # Below threshold
                features={"drop_pct": -3.0},
                processing_time_ms=120.0,
            ),
            PipelineResult(
                ticker="GOOGL",
                passed_filter=False,
                processing_time_ms=50.0,
            ),
        ]

        candidates = pipeline.get_candidates(results)

        assert len(candidates) == 1
        assert candidates[0]["ticker"] == "AAPL"
        assert candidates[0]["score"] == 0.8

    def test_get_candidates_empty(self):
        """Test candidate extraction with no qualified results."""
        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy, min_score=0.9)

        results = [
            PipelineResult(
                ticker="AAPL",
                passed_filter=True,
                score=0.5,  # Below threshold
                features={},
                processing_time_ms=100.0,
            ),
        ]

        candidates = pipeline.get_candidates(results)

        assert len(candidates) == 0

    def test_bars_to_dict_list(self):
        """Test conversion of DataFrame to dict list."""
        import pandas as pd

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        # Create sample DataFrame
        bars_df = pd.DataFrame(
            {
                "Open": [100.0, 101.0],
                "High": [102.0, 103.0],
                "Low": [99.0, 100.0],
                "Close": [101.0, 102.0],
                "Volume": [1000000, 1100000],
            },
            index=pd.DatetimeIndex(["2025-01-01", "2025-01-02"]),
        )

        bars_list = pipeline._bars_to_dict_list(bars_df)

        assert len(bars_list) == 2
        assert bars_list[0]["close"] == 101.0
        assert bars_list[0]["volume"] == 1000000
        assert "date" in bars_list[0]

    def test_bars_to_dict_list_empty(self):
        """Test conversion of empty DataFrame."""
        import pandas as pd

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        bars_df = pd.DataFrame()
        bars_list = pipeline._bars_to_dict_list(bars_df)

        assert bars_list == []

    def test_calculate_indicators(self):
        """Test indicator calculation from bars."""
        import pandas as pd

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        # Create sample DataFrame with sufficient data (using capital column names like yfinance)
        dates = pd.date_range("2025-01-01", periods=30, freq="D")
        bars_df = pd.DataFrame(
            {
                "Open": [100.0] * 30,
                "High": [102.0] * 30,
                "Low": [99.0] * 30,
                "Close": [101.0] * 30,
                "Volume": [1000000] * 30,
            },
            index=dates,
        )

        indicators = pipeline._calculate_indicators(bars_df)

        assert "rsi" in indicators
        assert "atr" in indicators
        assert "sma_20" in indicators
        assert "rvol" in indicators
        assert "volume_20d_avg" in indicators

    def test_calculate_indicators_insufficient_data(self):
        """Test indicator calculation with insufficient data."""
        import pandas as pd

        strategy = Drop5Strategy()
        pipeline = ScanPipeline(strategy)

        # Only 1 bar (insufficient)
        bars_df = pd.DataFrame(
            {
                "Open": [100.0],
                "High": [102.0],
                "Low": [99.0],
                "Close": [101.0],
                "Volume": [1000000],
            },
            index=pd.DatetimeIndex(["2025-01-01"]),
        )

        indicators = pipeline._calculate_indicators(bars_df)

        assert indicators == {}


class TestPipelineResult:
    """Test PipelineResult dataclass."""

    def test_result_creation(self):
        """Test creating a pipeline result."""
        result = PipelineResult(
            ticker="AAPL",
            passed_filter=True,
            features={"drop_pct": -7.0},
            score=0.75,
            processing_time_ms=123.45,
        )

        assert result.ticker == "AAPL"
        assert result.passed_filter is True
        assert result.features["drop_pct"] == -7.0
        assert result.score == 0.75
        assert result.error is None

    def test_result_with_error(self):
        """Test creating a result with error."""
        result = PipelineResult(
            ticker="INVALID",
            passed_filter=False,
            error="DataNotFoundError: No data",
            processing_time_ms=50.0,
        )

        assert result.ticker == "INVALID"
        assert result.passed_filter is False
        assert result.error is not None
        assert result.features is None
        assert result.score is None
