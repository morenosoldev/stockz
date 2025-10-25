"""Tests for data adapter base interfaces."""

from datetime import UTC, datetime

import pytest

from src.datasources.base import (
    Attribution,
    AuthenticationError,
    BaseDataAdapter,
    DataAdapterError,
    DataAdapterProtocol,
    DataNotFoundError,
    DataSource,
    RateLimitError,
)


class TestDataSource:
    """Test DataSource enum."""

    def test_data_source_values(self):
        """Test DataSource enum values."""
        assert DataSource.YAHOO_FINANCE.value == "yahoo_finance"
        assert DataSource.ALPHA_VANTAGE.value == "alpha_vantage"
        assert DataSource.FINNHUB.value == "finnhub"
        assert DataSource.NEWS_API.value == "news_api"
        assert DataSource.INTERNAL.value == "internal"
        assert DataSource.UNKNOWN.value == "unknown"

    def test_data_source_from_string(self):
        """Test creating DataSource from string."""
        source = DataSource("yahoo_finance")
        assert source == DataSource.YAHOO_FINANCE

    def test_invalid_data_source(self):
        """Test invalid data source raises error."""
        with pytest.raises(ValueError):
            DataSource("invalid_source")


class TestAttribution:
    """Test Attribution dataclass."""

    def test_create_attribution(self):
        """Test creating Attribution."""
        now = datetime.now(UTC)
        attr = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now,
            url="https://example.com",
            api_endpoint="/api/v1",
            version="2.0",
            metadata={"key": "value"},
        )

        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.timestamp == now
        assert attr.url == "https://example.com"
        assert attr.api_endpoint == "/api/v1"
        assert attr.version == "2.0"
        assert attr.metadata == {"key": "value"}

    def test_attribution_defaults(self):
        """Test Attribution with defaults."""
        now = datetime.now(UTC)
        attr = Attribution(source=DataSource.ALPHA_VANTAGE, timestamp=now)

        assert attr.source == DataSource.ALPHA_VANTAGE
        assert attr.timestamp == now
        assert attr.url is None
        assert attr.api_endpoint is None
        assert attr.version == "1.0"
        assert attr.metadata == {}

    def test_attribution_invalid_source_type(self):
        """Test Attribution with invalid source type."""
        now = datetime.now(UTC)
        with pytest.raises(TypeError, match="source must be DataSource enum"):
            Attribution(source="not_an_enum", timestamp=now)  # type: ignore

    def test_attribution_invalid_timestamp_type(self):
        """Test Attribution with invalid timestamp type."""
        with pytest.raises(TypeError, match="timestamp must be datetime"):
            Attribution(source=DataSource.YAHOO_FINANCE, timestamp="not_a_datetime")  # type: ignore


class TestDataAdapterError:
    """Test DataAdapterError exception."""

    def test_create_error(self):
        """Test creating DataAdapterError."""
        err = DataAdapterError("Test error")
        assert str(err) == "Test error"
        assert err.source is None
        assert err.original_error is None

    def test_error_with_source(self):
        """Test error with source."""
        err = DataAdapterError("Test error", source=DataSource.YAHOO_FINANCE)
        assert err.source == DataSource.YAHOO_FINANCE

    def test_error_with_original_error(self):
        """Test error wrapping another error."""
        original = ValueError("Original error")
        err = DataAdapterError("Wrapped error", original_error=original)
        assert err.original_error is original

    def test_rate_limit_error(self):
        """Test RateLimitError."""
        err = RateLimitError("Rate limit exceeded", source=DataSource.ALPHA_VANTAGE)
        assert str(err) == "Rate limit exceeded"
        assert err.source == DataSource.ALPHA_VANTAGE
        assert isinstance(err, DataAdapterError)

    def test_authentication_error(self):
        """Test AuthenticationError."""
        err = AuthenticationError("Invalid API key")
        assert str(err) == "Invalid API key"
        assert isinstance(err, DataAdapterError)

    def test_data_not_found_error(self):
        """Test DataNotFoundError."""
        err = DataNotFoundError("Data not available")
        assert str(err) == "Data not available"
        assert isinstance(err, DataAdapterError)


class TestDataAdapterProtocol:
    """Test DataAdapterProtocol."""

    def test_protocol_implementation(self):
        """Test implementing DataAdapterProtocol."""

        class TestAdapter:
            source = DataSource.YAHOO_FINANCE

            def fetch(self, *args, **kwargs):
                return {"data": "test"}

            def get_attribution(self):
                return Attribution(source=self.source, timestamp=datetime.now(UTC))

        adapter = TestAdapter()
        assert isinstance(adapter, DataAdapterProtocol)

    def test_protocol_missing_source(self):
        """Test protocol check with missing source."""

        class IncompleteAdapter:
            def fetch(self, *args, **kwargs):
                return {"data": "test"}

            def get_attribution(self):
                return Attribution(source=DataSource.YAHOO_FINANCE, timestamp=datetime.now(UTC))

        adapter = IncompleteAdapter()
        # Protocol check should fail (missing source attribute)
        assert not isinstance(adapter, DataAdapterProtocol)

    def test_protocol_missing_fetch(self):
        """Test protocol check with missing fetch method."""

        class IncompleteAdapter:
            source = DataSource.YAHOO_FINANCE

            def get_attribution(self):
                return Attribution(source=self.source, timestamp=datetime.now(UTC))

        adapter = IncompleteAdapter()
        # Protocol check should fail (missing fetch method)
        assert not isinstance(adapter, DataAdapterProtocol)


class TestBaseDataAdapter:
    """Test BaseDataAdapter abstract class."""

    def test_cannot_instantiate_directly(self):
        """Test that BaseDataAdapter cannot be instantiated."""
        with pytest.raises(TypeError):
            BaseDataAdapter()  # type: ignore

    def test_subclass_implementation(self):
        """Test implementing BaseDataAdapter."""

        class TestAdapter(BaseDataAdapter):
            source = DataSource.YAHOO_FINANCE

            def fetch(self, ticker: str):
                data = {"ticker": ticker, "price": 100.0}
                self._last_attribution = self._build_attribution(
                    url=f"https://api.example.com/{ticker}"
                )
                return data

            def _build_attribution(self, **metadata):
                return Attribution(
                    source=self.source,
                    timestamp=datetime.now(UTC),
                    **metadata,
                )

        adapter = TestAdapter()
        assert adapter.source == DataSource.YAHOO_FINANCE
        assert adapter.logger is not None

        # Test fetch
        data = adapter.fetch("AAPL")
        assert data["ticker"] == "AAPL"
        assert data["price"] == 100.0

        # Test attribution
        attr = adapter.get_attribution()
        assert attr.source == DataSource.YAHOO_FINANCE
        assert "https://api.example.com/AAPL" in str(attr.url)

    def test_get_attribution_before_fetch(self):
        """Test get_attribution before any fetch raises error."""

        class TestAdapter(BaseDataAdapter):
            source = DataSource.YAHOO_FINANCE

            def fetch(self, *args, **kwargs):
                return {}

            def _build_attribution(self, **metadata):
                return Attribution(source=self.source, timestamp=datetime.now(UTC))

        adapter = TestAdapter()
        with pytest.raises(ValueError, match="No fetch operation performed yet"):
            adapter.get_attribution()

    def test_validate_data_default(self):
        """Test default validate_data implementation."""

        class TestAdapter(BaseDataAdapter):
            source = DataSource.YAHOO_FINANCE

            def fetch(self, *args, **kwargs):
                return {}

            def _build_attribution(self, **metadata):
                return Attribution(source=self.source, timestamp=datetime.now(UTC))

        adapter = TestAdapter()
        assert adapter.validate_data({"data": "test"}) is True
        assert adapter.validate_data(None) is False

    def test_validate_data_override(self):
        """Test overriding validate_data."""

        class TestAdapter(BaseDataAdapter):
            source = DataSource.YAHOO_FINANCE

            def fetch(self, *args, **kwargs):
                return {}

            def _build_attribution(self, **metadata):
                return Attribution(source=self.source, timestamp=datetime.now(UTC))

            def validate_data(self, data):
                return isinstance(data, dict) and "price" in data

        adapter = TestAdapter()
        assert adapter.validate_data({"price": 100.0}) is True
        assert adapter.validate_data({"other": "data"}) is False
        assert adapter.validate_data(None) is False

    def test_subclass_missing_fetch(self):
        """Test subclass must implement fetch."""

        # Can't even instantiate without implementing abstract methods
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):

            class IncompleteAdapter(BaseDataAdapter):
                source = DataSource.YAHOO_FINANCE

                def _build_attribution(self, **metadata):
                    return Attribution(source=self.source, timestamp=datetime.now(UTC))

            IncompleteAdapter()

    def test_subclass_missing_build_attribution(self):
        """Test subclass must implement _build_attribution."""

        # Can't even instantiate without implementing abstract methods
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):

            class IncompleteAdapter(BaseDataAdapter):
                source = DataSource.YAHOO_FINANCE

                def fetch(self, *args, **kwargs):
                    return {}

            IncompleteAdapter()
