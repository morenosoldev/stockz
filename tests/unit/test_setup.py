"""Basic tests to verify project setup."""


def test_imports() -> None:
    """Test that basic imports work."""
    import src

    assert src.__version__ == "1.0.0"


def test_sample_fixture(sample_ticker: str) -> None:
    """Test that pytest fixtures work."""
    assert sample_ticker == "AAPL"
    assert isinstance(sample_ticker, str)


def test_sample_tickers_fixture(sample_tickers: list[str]) -> None:
    """Test that list fixtures work."""
    assert len(sample_tickers) == 5
    assert "AAPL" in sample_tickers
