"""Test suite configuration and fixtures."""

import pytest


@pytest.fixture
def sample_ticker() -> str:
    """Return a sample ticker symbol for testing."""
    return "AAPL"


@pytest.fixture
def sample_tickers() -> list[str]:
    """Return a list of sample ticker symbols for testing."""
    return ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
