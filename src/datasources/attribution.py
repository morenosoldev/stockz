"""Attribution tracking utilities for data sources.

This module provides utilities for tracking, validating, and serializing
attribution metadata for all data fetched from external sources.

Attribution ensures reproducibility, compliance, and data lineage tracking.
"""

import json
from datetime import UTC, datetime
from typing import Any

from src.datasources.base import Attribution, DataSource
from src.ops.logging import get_logger

__all__ = [
    "Attribution",
    "AttributionError",
    "create_attribution",
    "validate_attribution",
    "serialize_attribution",
]

logger = get_logger(__name__)


class AttributionError(Exception):
    """Exception raised when attribution validation fails."""

    pass


def create_attribution(
    source: DataSource | str,
    url: str | None = None,
    api_endpoint: str | None = None,
    version: str = "1.0",
    **metadata: Any,
) -> Attribution:
    """Create an Attribution instance with validation.

    Args:
        source: Data source identifier (enum or string)
        url: Optional URL of the data source endpoint
        api_endpoint: Optional API endpoint path
        version: Data schema version
        **metadata: Additional metadata

    Returns:
        Validated Attribution instance

    Raises:
        AttributionError: If validation fails

    Example:
        >>> attr = create_attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     url="https://query1.finance.yahoo.com/v8/finance/chart/AAPL",
        ...     api_endpoint="/v8/finance/chart/AAPL",
        ...     metadata={"request_id": "abc123"}
        ... )
    """
    # Convert string source to enum
    if isinstance(source, str):
        try:
            source = DataSource(source)
        except ValueError as e:
            raise AttributionError(f"Invalid data source: {source}") from e

    # Create attribution with current UTC timestamp
    try:
        attribution = Attribution(
            source=source,
            timestamp=datetime.now(UTC),
            url=url,
            api_endpoint=api_endpoint,
            version=version,
            metadata=metadata,
        )
        return attribution
    except (TypeError, ValueError) as e:
        raise AttributionError(f"Failed to create attribution: {e}") from e


def validate_attribution(attribution: Attribution) -> bool:
    """Validate an Attribution instance.

    Checks that:
    - source is a valid DataSource enum
    - timestamp is a datetime object
    - timestamp is not in the future (with 1 minute tolerance)
    - version follows semantic versioning pattern

    Args:
        attribution: Attribution to validate

    Returns:
        True if attribution is valid

    Raises:
        AttributionError: If validation fails

    Example:
        >>> attr = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc)
        ... )
        >>> validate_attribution(attr)
        True
    """
    # Check source type
    if not isinstance(attribution.source, DataSource):
        raise AttributionError(
            f"Invalid source type: expected DataSource, got {type(attribution.source)}"
        )

    # Check timestamp type
    if not isinstance(attribution.timestamp, datetime):
        raise AttributionError(
            f"Invalid timestamp type: expected datetime, got {type(attribution.timestamp)}"
        )

    # Check timestamp is not in future (with 1 minute tolerance for clock skew)
    now = datetime.now(UTC)
    # Normalize both timestamps to naive UTC for comparison
    timestamp_naive = (
        attribution.timestamp.replace(tzinfo=None)
        if attribution.timestamp.tzinfo is not None
        else attribution.timestamp
    )
    now_naive = now.replace(tzinfo=None)

    if timestamp_naive > now_naive:
        # Allow 1 minute tolerance for clock skew
        delta = (timestamp_naive - now_naive).total_seconds()
        if delta > 60:
            raise AttributionError(f"Timestamp is in the future: {attribution.timestamp} > {now}")

    # Check version format (basic check)
    if not attribution.version or not isinstance(attribution.version, str):
        raise AttributionError(f"Invalid version: {attribution.version}")

    return True


def serialize_attribution(attribution: Attribution) -> dict[str, Any]:
    """Serialize Attribution to a JSON-compatible dictionary.

    Args:
        attribution: Attribution to serialize

    Returns:
        Dictionary representation suitable for JSON serialization

    Example:
        >>> attr = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc)
        ... )
        >>> data = serialize_attribution(attr)
        >>> data["source"]
        'yahoo_finance'
    """
    return {
        "source": attribution.source.value,
        "timestamp": attribution.timestamp.isoformat(),
        "url": attribution.url,
        "api_endpoint": attribution.api_endpoint,
        "version": attribution.version,
        "metadata": attribution.metadata,
    }


def deserialize_attribution(data: dict[str, Any]) -> Attribution:
    """Deserialize Attribution from a dictionary.

    Args:
        data: Dictionary containing attribution data

    Returns:
        Attribution instance

    Raises:
        AttributionError: If deserialization fails

    Example:
        >>> data = {
        ...     "source": "yahoo_finance",
        ...     "timestamp": "2025-10-24T12:00:00Z",
        ...     "version": "1.0"
        ... }
        >>> attr = deserialize_attribution(data)
        >>> attr.source == DataSource.YAHOO_FINANCE
        True
    """
    try:
        # Parse source enum
        source = DataSource(data["source"])

        # Parse timestamp
        timestamp_str = data["timestamp"]
        # Handle ISO format with Z suffix
        if timestamp_str.endswith("Z"):
            timestamp_str = timestamp_str[:-1] + "+00:00"
        timestamp = datetime.fromisoformat(timestamp_str)

        # Create attribution
        attribution = Attribution(
            source=source,
            timestamp=timestamp,
            url=data.get("url"),
            api_endpoint=data.get("api_endpoint"),
            version=data.get("version", "1.0"),
            metadata=data.get("metadata", {}),
        )

        # Validate before returning
        validate_attribution(attribution)
        return attribution

    except (KeyError, ValueError, TypeError) as e:
        raise AttributionError(f"Failed to deserialize attribution: {e}") from e


def attribution_to_json(attribution: Attribution) -> str:
    """Convert Attribution to JSON string.

    Args:
        attribution: Attribution to convert

    Returns:
        JSON string representation

    Example:
        >>> attr = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc)
        ... )
        >>> json_str = attribution_to_json(attr)
        >>> "yahoo_finance" in json_str
        True
    """
    return json.dumps(serialize_attribution(attribution), indent=2)


def attribution_from_json(json_str: str) -> Attribution:
    """Parse Attribution from JSON string.

    Args:
        json_str: JSON string containing attribution data

    Returns:
        Attribution instance

    Raises:
        AttributionError: If parsing fails

    Example:
        >>> json_str = '{"source": "yahoo_finance", "timestamp": "2025-10-24T12:00:00Z"}'
        >>> attr = attribution_from_json(json_str)
        >>> attr.source == DataSource.YAHOO_FINANCE
        True
    """
    try:
        data = json.loads(json_str)
        return deserialize_attribution(data)
    except json.JSONDecodeError as e:
        raise AttributionError(f"Invalid JSON: {e}") from e


def merge_attributions(*attributions: Attribution) -> Attribution:
    """Merge multiple attributions into one.

    Uses the earliest timestamp and combines metadata from all attributions.
    All attributions must be from the same source.

    Args:
        *attributions: Attributions to merge

    Returns:
        Merged attribution

    Raises:
        AttributionError: If attributions are from different sources or empty

    Example:
        >>> attr1 = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc),
        ...     metadata={"key1": "value1"}
        ... )
        >>> attr2 = Attribution(
        ...     source=DataSource.YAHOO_FINANCE,
        ...     timestamp=datetime.now(timezone.utc),
        ...     metadata={"key2": "value2"}
        ... )
        >>> merged = merge_attributions(attr1, attr2)
        >>> "key1" in merged.metadata and "key2" in merged.metadata
        True
    """
    if not attributions:
        raise AttributionError("Cannot merge empty attributions")

    # Check all attributions are from same source
    sources = {attr.source for attr in attributions}
    if len(sources) > 1:
        raise AttributionError(f"Cannot merge attributions from different sources: {sources}")

    # Find earliest timestamp
    earliest = min(attributions, key=lambda a: a.timestamp)

    # Merge metadata
    merged_metadata: dict[str, Any] = {}
    for attr in attributions:
        merged_metadata.update(attr.metadata)

    # Collect URLs and endpoints
    urls = [attr.url for attr in attributions if attr.url]
    endpoints = [attr.api_endpoint for attr in attributions if attr.api_endpoint]

    return Attribution(
        source=earliest.source,
        timestamp=earliest.timestamp,
        url=urls[0] if urls else None,
        api_endpoint=endpoints[0] if endpoints else None,
        version=earliest.version,
        metadata=merged_metadata,
    )
