"""
Feature Versioning System.

Provides utilities for tracking feature versions to ensure reproducibility
across different runs and strategy iterations.

All feature calculations should be versioned so that:
1. We can reproduce historical analysis with exact feature definitions
2. We can track which feature versions were used in which runs
3. We can safely upgrade features without breaking historical data
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import pandas as pd


@dataclass
class FeatureVersion:
    """
    Metadata for a feature calculation version.

    Attributes:
        name: Feature name (e.g., "RSI", "RVOL", "drop_detection")
        version: Semantic version string (e.g., "1.0.0")
        description: Human-readable description of this version
        parameters: Parameters used in calculation (e.g., {"period": 14})
        created_at: Timestamp when this version was created
        checksum: MD5 hash of feature logic (for detecting code changes)
    """

    name: str
    version: str
    description: str
    parameters: dict[str, Any]
    created_at: str
    checksum: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureVersion":
        """Create from dictionary."""
        return cls(**data)

    def __str__(self) -> str:
        """String representation."""
        return f"{self.name}@{self.version}"


class FeatureVersionRegistry:
    """
    Registry for tracking feature versions.

    This registry maintains a mapping of feature names to their versions,
    ensuring that we can always reproduce feature calculations.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._versions: dict[str, list[FeatureVersion]] = {}

    def register(
        self,
        name: str,
        version: str,
        description: str,
        parameters: dict[str, Any],
        code_hash: str | None = None,
    ) -> FeatureVersion:
        """
        Register a new feature version.

        Args:
            name: Feature name
            version: Semantic version (e.g., "1.0.0")
            description: Human-readable description
            parameters: Feature parameters (e.g., {"period": 14})
            code_hash: MD5 hash of feature code (optional, auto-generated if None)

        Returns:
            FeatureVersion object

        Raises:
            ValueError: If version already exists for this feature

        Example:
            >>> registry = FeatureVersionRegistry()
            >>> fv = registry.register(
            ...     name="RSI",
            ...     version="1.0.0",
            ...     description="Relative Strength Index",
            ...     parameters={"period": 14}
            ... )
        """
        # Check if version already exists
        if name in self._versions:
            for fv in self._versions[name]:
                if fv.version == version:
                    raise ValueError(f"Version {version} already exists for feature {name}")

        # Generate code hash if not provided
        if code_hash is None:
            code_hash = self._generate_hash(name, version, parameters)

        # Create feature version
        feature_version = FeatureVersion(
            name=name,
            version=version,
            description=description,
            parameters=parameters,
            created_at=datetime.now().isoformat(),
            checksum=code_hash,
        )

        # Add to registry
        if name not in self._versions:
            self._versions[name] = []
        self._versions[name].append(feature_version)

        return feature_version

    def get(self, name: str, version: str | None = None) -> FeatureVersion:
        """
        Get a specific feature version.

        Args:
            name: Feature name
            version: Specific version (if None, returns latest)

        Returns:
            FeatureVersion object

        Raises:
            KeyError: If feature not found
            ValueError: If version not found

        Example:
            >>> registry = FeatureVersionRegistry()
            >>> registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})
            >>> fv = registry.get("RSI", "1.0.0")
        """
        if name not in self._versions:
            raise KeyError(f"Feature {name} not found in registry")

        if version is None:
            # Return latest version
            return self._versions[name][-1]

        # Find specific version
        for fv in self._versions[name]:
            if fv.version == version:
                return fv

        raise ValueError(f"Version {version} not found for feature {name}")

    def get_all(self, name: str) -> list[FeatureVersion]:
        """
        Get all versions of a feature.

        Args:
            name: Feature name

        Returns:
            List of FeatureVersion objects

        Raises:
            KeyError: If feature not found
        """
        if name not in self._versions:
            raise KeyError(f"Feature {name} not found in registry")

        return self._versions[name]

    def list_features(self) -> list[str]:
        """
        List all registered feature names.

        Returns:
            List of feature names
        """
        return list(self._versions.keys())

    def to_dict(self) -> dict[str, Any]:
        """
        Export registry to dictionary.

        Returns:
            Dictionary representation of entire registry
        """
        return {
            name: [fv.to_dict() for fv in versions] for name, versions in self._versions.items()
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeatureVersionRegistry":
        """
        Import registry from dictionary.

        Args:
            data: Dictionary representation of registry

        Returns:
            FeatureVersionRegistry object
        """
        registry = cls()
        for name, versions in data.items():
            registry._versions[name] = [FeatureVersion.from_dict(fv) for fv in versions]
        return registry

    def _generate_hash(self, name: str, version: str, parameters: dict[str, Any]) -> str:
        """Generate MD5 hash for feature definition."""
        # Create deterministic string representation
        data_str = json.dumps(
            {"name": name, "version": version, "parameters": parameters}, sort_keys=True
        )
        return hashlib.md5(data_str.encode()).hexdigest()


def version_dataframe(
    df: pd.DataFrame, feature_versions: dict[str, FeatureVersion]
) -> pd.DataFrame:
    """
    Attach feature version metadata to DataFrame columns.

    This adds version information to DataFrame attributes so we can
    track which feature versions were used.

    Args:
        df: DataFrame with features
        feature_versions: Mapping of column names to FeatureVersion objects

    Returns:
        DataFrame with version metadata attached

    Example:
        >>> df = pd.DataFrame({"rsi": [30, 40, 50]})
        >>> fv = FeatureVersion("RSI", "1.0.0", "RSI", {"period": 14}, "2025-01-01", "abc123")
        >>> versioned_df = version_dataframe(df, {"rsi": fv})
    """
    # Attach version metadata as DataFrame attribute
    df.attrs["feature_versions"] = {col: fv.to_dict() for col, fv in feature_versions.items()}

    return df


def get_feature_versions(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """
    Extract feature version metadata from DataFrame.

    Args:
        df: DataFrame with version metadata

    Returns:
        Dictionary of feature versions

    Example:
        >>> versioned_df.attrs["feature_versions"]
        {'rsi': {'name': 'RSI', 'version': '1.0.0', ...}}
    """
    versions: dict[str, dict[str, Any]] = df.attrs.get("feature_versions", {})
    return versions


def validate_feature_versions(df: pd.DataFrame, expected_versions: dict[str, str]) -> bool:
    """
    Validate that DataFrame features match expected versions.

    Args:
        df: DataFrame with version metadata
        expected_versions: Mapping of feature names to expected versions

    Returns:
        True if all versions match, False otherwise

    Example:
        >>> versioned_df = version_dataframe(df, {"rsi": fv})
        >>> validate_feature_versions(versioned_df, {"rsi": "1.0.0"})
        True
    """
    actual_versions = get_feature_versions(df)

    for feature_name, expected_version in expected_versions.items():
        if feature_name not in actual_versions:
            return False

        actual_version = actual_versions[feature_name].get("version")
        if actual_version != expected_version:
            return False

    return True


def create_feature_snapshot(
    df: pd.DataFrame,
    feature_versions: dict[str, FeatureVersion],
    snapshot_id: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Create a snapshot of features with version information.

    This creates a serializable snapshot that includes:
    - Feature data
    - Feature versions
    - Metadata (e.g., ticker, date, strategy)

    Args:
        df: DataFrame with feature data
        feature_versions: Mapping of feature names to versions
        snapshot_id: Unique identifier for this snapshot
        metadata: Additional metadata (e.g., {"ticker": "AAPL", "date": "2025-10-24"})

    Returns:
        Dictionary containing snapshot data

    Example:
        >>> snapshot = create_feature_snapshot(
        ...     df,
        ...     {"rsi": fv},
        ...     "AAPL_2025-10-24",
        ...     {"ticker": "AAPL", "date": "2025-10-24"}
        ... )
    """
    snapshot = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now().isoformat(),
        "feature_data": df.to_dict(orient="records"),
        "feature_versions": {name: fv.to_dict() for name, fv in feature_versions.items()},
        "metadata": metadata or {},
    }

    return snapshot


def load_feature_snapshot(
    snapshot: dict[str, Any],
) -> tuple[pd.DataFrame, dict[str, FeatureVersion]]:
    """
    Load feature data from a snapshot.

    Args:
        snapshot: Snapshot dictionary created by create_feature_snapshot

    Returns:
        Tuple of (DataFrame, feature_versions)

    Example:
        >>> df, versions = load_feature_snapshot(snapshot)
    """
    # Reconstruct DataFrame
    df = pd.DataFrame(snapshot["feature_data"])

    # Reconstruct feature versions
    feature_versions = {
        name: FeatureVersion.from_dict(fv_data)
        for name, fv_data in snapshot["feature_versions"].items()
    }

    # Attach versions to DataFrame
    df = version_dataframe(df, feature_versions)

    return df, feature_versions
