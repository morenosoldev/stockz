"""Tests for attribution utilities."""

from datetime import UTC, datetime, timedelta

import pytest

from src.datasources.attribution import (
    AttributionError,
    attribution_from_json,
    attribution_to_json,
    create_attribution,
    deserialize_attribution,
    merge_attributions,
    serialize_attribution,
    validate_attribution,
)
from src.datasources.base import Attribution, DataSource


class TestCreateAttribution:
    """Test create_attribution function."""

    def test_create_with_enum(self):
        """Test creating attribution with DataSource enum."""
        attr = create_attribution(source=DataSource.YAHOO_FINANCE)
        assert attr.source == DataSource.YAHOO_FINANCE
        assert isinstance(attr.timestamp, datetime)
        assert attr.version == "1.0"

    def test_create_with_string(self):
        """Test creating attribution with string source."""
        attr = create_attribution(source="yahoo_finance")
        assert attr.source == DataSource.YAHOO_FINANCE

    def test_create_with_metadata(self):
        """Test creating attribution with metadata."""
        attr = create_attribution(
            source=DataSource.ALPHA_VANTAGE,
            url="https://api.example.com",
            api_endpoint="/v1/data",
            version="2.0",
            request_id="abc123",
            rate_limit=5,
        )
        assert attr.url == "https://api.example.com"
        assert attr.api_endpoint == "/v1/data"
        assert attr.version == "2.0"
        assert attr.metadata["request_id"] == "abc123"
        assert attr.metadata["rate_limit"] == 5

    def test_create_invalid_source(self):
        """Test creating attribution with invalid source."""
        with pytest.raises(AttributionError, match="Invalid data source"):
            create_attribution(source="invalid_source")

    def test_timestamp_is_utc(self):
        """Test that timestamp is in UTC."""
        before = datetime.now(UTC).replace(tzinfo=None)
        attr = create_attribution(source=DataSource.YAHOO_FINANCE)
        after = datetime.now(UTC).replace(tzinfo=None)

        # Normalize attr timestamp to naive for comparison
        attr_timestamp = (
            attr.timestamp.replace(tzinfo=None)
            if attr.timestamp.tzinfo is not None
            else attr.timestamp
        )
        assert before <= attr_timestamp <= after


class TestValidateAttribution:
    """Test validate_attribution function."""

    def test_valid_attribution(self):
        """Test validating valid attribution."""
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=datetime.now(UTC))
        assert validate_attribution(attr) is True

    def test_invalid_source_type(self):
        """Test validation fails with invalid source type."""
        # Create Attribution with valid source first
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=datetime.now(UTC))
        # Then modify it to have invalid source (bypassing validation)
        attr.source = "not_an_enum"  # type: ignore
        with pytest.raises(AttributionError, match="Invalid source type"):
            validate_attribution(attr)

    def test_invalid_timestamp_type(self):
        """Test validation fails with invalid timestamp type."""
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=datetime.now(UTC))
        attr.timestamp = "not_a_datetime"  # type: ignore
        with pytest.raises(AttributionError, match="Invalid timestamp type"):
            validate_attribution(attr)

    def test_future_timestamp(self):
        """Test validation fails with future timestamp."""
        future_time = datetime.now(UTC) + timedelta(hours=2)
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=future_time)
        with pytest.raises(AttributionError, match="Timestamp is in the future"):
            validate_attribution(attr)

    def test_future_timestamp_within_tolerance(self):
        """Test future timestamp within 1 minute tolerance is accepted."""
        # 30 seconds in future (within 1 minute tolerance)
        future_time = datetime.now(UTC) + timedelta(seconds=30)
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=future_time)
        assert validate_attribution(attr) is True

    def test_invalid_version(self):
        """Test validation fails with invalid version."""
        attr = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=datetime.now(UTC),
            version="",
        )
        with pytest.raises(AttributionError, match="Invalid version"):
            validate_attribution(attr)

    def test_none_version(self):
        """Test validation fails with None version."""
        attr = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=datetime.now(UTC),
            version=None,  # type: ignore
        )
        with pytest.raises(AttributionError, match="Invalid version"):
            validate_attribution(attr)


class TestSerializeAttribution:
    """Test serialize_attribution function."""

    def test_serialize_basic(self):
        """Test serializing basic attribution."""
        now = datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC)
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now)

        data = serialize_attribution(attr)
        assert data["source"] == "yahoo_finance"
        assert data["timestamp"] == "2025-10-24T12:00:00+00:00"
        assert data["url"] is None
        assert data["api_endpoint"] is None
        assert data["version"] == "1.0"
        assert data["metadata"] == {}

    def test_serialize_full(self):
        """Test serializing attribution with all fields."""
        now = datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC)
        attr = Attribution(
            source=DataSource.ALPHA_VANTAGE,
            timestamp=now,
            url="https://api.example.com",
            api_endpoint="/v1/data",
            version="2.0",
            metadata={"key": "value"},
        )

        data = serialize_attribution(attr)
        assert data["source"] == "alpha_vantage"
        assert data["url"] == "https://api.example.com"
        assert data["api_endpoint"] == "/v1/data"
        assert data["version"] == "2.0"
        assert data["metadata"] == {"key": "value"}


class TestDeserializeAttribution:
    """Test deserialize_attribution function."""

    def test_deserialize_basic(self):
        """Test deserializing basic attribution."""
        data = {
            "source": "yahoo_finance",
            "timestamp": "2025-10-24T12:00:00+00:00",
        }
        attr = deserialize_attribution(data)
        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.timestamp.year == 2025
        assert attr.version == "1.0"

    def test_deserialize_with_z_suffix(self):
        """Test deserializing timestamp with Z suffix."""
        data = {
            "source": "yahoo_finance",
            "timestamp": "2025-10-24T12:00:00Z",
        }
        attr = deserialize_attribution(data)
        assert attr.timestamp.year == 2025

    def test_deserialize_full(self):
        """Test deserializing attribution with all fields."""
        data = {
            "source": "alpha_vantage",
            "timestamp": "2025-10-24T12:00:00+00:00",
            "url": "https://api.example.com",
            "api_endpoint": "/v1/data",
            "version": "2.0",
            "metadata": {"key": "value"},
        }
        attr = deserialize_attribution(data)
        assert attr.source == DataSource.ALPHA_VANTAGE
        assert attr.url == "https://api.example.com"
        assert attr.api_endpoint == "/v1/data"
        assert attr.version == "2.0"
        assert attr.metadata == {"key": "value"}

    def test_deserialize_missing_source(self):
        """Test deserialization fails with missing source."""
        data = {"timestamp": "2025-10-24T12:00:00+00:00"}
        with pytest.raises(AttributionError, match="Failed to deserialize"):
            deserialize_attribution(data)

    def test_deserialize_invalid_source(self):
        """Test deserialization fails with invalid source."""
        data = {
            "source": "invalid_source",
            "timestamp": "2025-10-24T12:00:00+00:00",
        }
        with pytest.raises(AttributionError, match="Failed to deserialize"):
            deserialize_attribution(data)

    def test_deserialize_invalid_timestamp(self):
        """Test deserialization fails with invalid timestamp."""
        data = {
            "source": "yahoo_finance",
            "timestamp": "not_a_timestamp",
        }
        with pytest.raises(AttributionError, match="Failed to deserialize"):
            deserialize_attribution(data)


class TestAttributionJson:
    """Test JSON serialization/deserialization."""

    def test_to_json(self):
        """Test converting attribution to JSON."""
        now = datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC)
        attr = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now)

        json_str = attribution_to_json(attr)
        assert isinstance(json_str, str)
        assert "yahoo_finance" in json_str
        assert "2025-10-24" in json_str

    def test_from_json(self):
        """Test parsing attribution from JSON."""
        json_str = """{
            "source": "yahoo_finance",
            "timestamp": "2025-10-24T12:00:00Z"
        }"""
        attr = attribution_from_json(json_str)
        assert attr.source == DataSource.YAHOO_FINANCE
        assert attr.timestamp.year == 2025

    def test_roundtrip(self):
        """Test JSON roundtrip preserves data."""
        original = Attribution(
            source=DataSource.ALPHA_VANTAGE,
            timestamp=datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC),
            url="https://api.example.com",
            version="2.0",
            metadata={"key": "value"},
        )

        json_str = attribution_to_json(original)
        restored = attribution_from_json(json_str)

        assert restored.source == original.source
        assert restored.url == original.url
        assert restored.version == original.version
        assert restored.metadata == original.metadata

    def test_from_json_invalid(self):
        """Test parsing invalid JSON raises error."""
        with pytest.raises(AttributionError, match="Invalid JSON"):
            attribution_from_json("not valid json")


class TestMergeAttributions:
    """Test merge_attributions function."""

    def test_merge_two_attributions(self):
        """Test merging two attributions."""
        now1 = datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC)
        now2 = datetime(2025, 10, 24, 12, 5, 0, tzinfo=UTC)

        attr1 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now1,
            metadata={"key1": "value1"},
        )
        attr2 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now2,
            metadata={"key2": "value2"},
        )

        merged = merge_attributions(attr1, attr2)
        assert merged.source == DataSource.YAHOO_FINANCE
        assert merged.timestamp == now1  # Earliest timestamp
        assert "key1" in merged.metadata
        assert "key2" in merged.metadata

    def test_merge_empty(self):
        """Test merging empty attributions raises error."""
        with pytest.raises(AttributionError, match="Cannot merge empty"):
            merge_attributions()

    def test_merge_different_sources(self):
        """Test merging attributions from different sources raises error."""
        now = datetime.now(UTC)
        attr1 = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now)
        attr2 = Attribution(source=DataSource.ALPHA_VANTAGE, timestamp=now)

        with pytest.raises(
            AttributionError, match="Cannot merge attributions from different sources"
        ):
            merge_attributions(attr1, attr2)

    def test_merge_picks_earliest_timestamp(self):
        """Test merge picks earliest timestamp."""
        now1 = datetime(2025, 10, 24, 14, 0, 0, tzinfo=UTC)
        now2 = datetime(2025, 10, 24, 12, 0, 0, tzinfo=UTC)  # Earlier
        now3 = datetime(2025, 10, 24, 13, 0, 0, tzinfo=UTC)

        attr1 = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now1)
        attr2 = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now2)
        attr3 = Attribution(source=DataSource.YAHOO_FINANCE, timestamp=now3)

        merged = merge_attributions(attr1, attr2, attr3)
        assert merged.timestamp == now2

    def test_merge_combines_metadata(self):
        """Test merge combines all metadata."""
        now = datetime.now(UTC)
        attr1 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now,
            metadata={"a": 1, "b": 2},
        )
        attr2 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now,
            metadata={"c": 3, "d": 4},
        )

        merged = merge_attributions(attr1, attr2)
        assert merged.metadata == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_merge_picks_first_url(self):
        """Test merge picks first URL."""
        now = datetime.now(UTC)
        attr1 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now,
            url="https://url1.com",
        )
        attr2 = Attribution(
            source=DataSource.YAHOO_FINANCE,
            timestamp=now,
            url="https://url2.com",
        )

        merged = merge_attributions(attr1, attr2)
        assert merged.url == "https://url1.com"
