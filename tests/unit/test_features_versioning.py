"""
Tests for feature versioning system.

Tests cover feature version registration, DataFrame versioning,
and snapshot creation/loading.
"""

import pandas as pd
import pytest

from src.features.versioning import (
    FeatureVersion,
    FeatureVersionRegistry,
    create_feature_snapshot,
    get_feature_versions,
    load_feature_snapshot,
    validate_feature_versions,
    version_dataframe,
)


class TestFeatureVersion:
    """Tests for FeatureVersion dataclass."""

    def test_create_feature_version(self):
        """Test creating a FeatureVersion."""
        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="Relative Strength Index",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        assert fv.name == "RSI"
        assert fv.version == "1.0.0"
        assert fv.parameters["period"] == 14

    def test_to_dict(self):
        """Test converting FeatureVersion to dict."""
        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="Relative Strength Index",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        fv_dict = fv.to_dict()

        assert fv_dict["name"] == "RSI"
        assert fv_dict["version"] == "1.0.0"
        assert fv_dict["parameters"]["period"] == 14

    def test_from_dict(self):
        """Test creating FeatureVersion from dict."""
        fv_dict = {
            "name": "RSI",
            "version": "1.0.0",
            "description": "Relative Strength Index",
            "parameters": {"period": 14},
            "created_at": "2025-10-24T00:00:00",
            "checksum": "abc123",
        }

        fv = FeatureVersion.from_dict(fv_dict)

        assert fv.name == "RSI"
        assert fv.version == "1.0.0"
        assert fv.parameters["period"] == 14

    def test_str_representation(self):
        """Test string representation."""
        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="Relative Strength Index",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        assert str(fv) == "RSI@1.0.0"


class TestFeatureVersionRegistry:
    """Tests for FeatureVersionRegistry."""

    def test_register_feature(self):
        """Test registering a new feature version."""
        registry = FeatureVersionRegistry()

        fv = registry.register(
            name="RSI",
            version="1.0.0",
            description="Relative Strength Index",
            parameters={"period": 14},
        )

        assert fv.name == "RSI"
        assert fv.version == "1.0.0"
        assert fv.checksum is not None

    def test_register_duplicate_version(self):
        """Test that duplicate versions raise error."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})

        with pytest.raises(ValueError, match="already exists"):
            registry.register("RSI", "1.0.0", "RSI v1 duplicate", {"period": 14})

    def test_register_multiple_versions(self):
        """Test registering multiple versions of same feature."""
        registry = FeatureVersionRegistry()

        fv1 = registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})
        fv2 = registry.register("RSI", "2.0.0", "RSI v2", {"period": 21})

        assert fv1.version == "1.0.0"
        assert fv2.version == "2.0.0"

    def test_get_specific_version(self):
        """Test getting a specific version."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})
        registry.register("RSI", "2.0.0", "RSI v2", {"period": 21})

        fv = registry.get("RSI", "1.0.0")

        assert fv.version == "1.0.0"
        assert fv.parameters["period"] == 14

    def test_get_latest_version(self):
        """Test getting latest version (no version specified)."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})
        registry.register("RSI", "2.0.0", "RSI v2", {"period": 21})

        fv = registry.get("RSI")

        assert fv.version == "2.0.0"
        assert fv.parameters["period"] == 21

    def test_get_nonexistent_feature(self):
        """Test getting non-existent feature."""
        registry = FeatureVersionRegistry()

        with pytest.raises(KeyError):
            registry.get("NonExistent")

    def test_get_nonexistent_version(self):
        """Test getting non-existent version."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})

        with pytest.raises(ValueError):
            registry.get("RSI", "99.0.0")

    def test_get_all_versions(self):
        """Test getting all versions of a feature."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI v1", {"period": 14})
        registry.register("RSI", "2.0.0", "RSI v2", {"period": 21})

        all_versions = registry.get_all("RSI")

        assert len(all_versions) == 2
        assert all_versions[0].version == "1.0.0"
        assert all_versions[1].version == "2.0.0"

    def test_list_features(self):
        """Test listing all features."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI", {"period": 14})
        registry.register("ATR", "1.0.0", "ATR", {"period": 14})
        registry.register("RVOL", "1.0.0", "RVOL", {"period": 20})

        features = registry.list_features()

        assert "RSI" in features
        assert "ATR" in features
        assert "RVOL" in features
        assert len(features) == 3

    def test_to_dict(self):
        """Test exporting registry to dict."""
        registry = FeatureVersionRegistry()

        registry.register("RSI", "1.0.0", "RSI", {"period": 14})
        registry.register("RSI", "2.0.0", "RSI v2", {"period": 21})

        registry_dict = registry.to_dict()

        assert "RSI" in registry_dict
        assert len(registry_dict["RSI"]) == 2
        assert registry_dict["RSI"][0]["version"] == "1.0.0"

    def test_from_dict(self):
        """Test importing registry from dict."""
        registry_dict = {
            "RSI": [
                {
                    "name": "RSI",
                    "version": "1.0.0",
                    "description": "RSI",
                    "parameters": {"period": 14},
                    "created_at": "2025-10-24T00:00:00",
                    "checksum": "abc123",
                }
            ]
        }

        registry = FeatureVersionRegistry.from_dict(registry_dict)

        fv = registry.get("RSI", "1.0.0")
        assert fv.name == "RSI"
        assert fv.parameters["period"] == 14

    def test_checksum_generation(self):
        """Test that checksum is auto-generated."""
        registry = FeatureVersionRegistry()

        fv1 = registry.register("RSI", "1.0.0", "RSI", {"period": 14})
        fv2 = registry.register("RVOL", "1.0.0", "RVOL", {"period": 14})

        # Different features should have different checksums
        assert fv1.checksum != fv2.checksum
        # But both should have checksums generated
        assert fv1.checksum is not None
        assert fv2.checksum is not None

    def test_checksum_differs_with_parameters(self):
        """Test that checksum differs with different parameters."""
        registry = FeatureVersionRegistry()

        fv1 = registry.register("RSI", "1.0.0", "RSI", {"period": 14})
        fv2 = registry.register("RSI", "2.0.0", "RSI", {"period": 21})

        # Different parameters should give different checksum
        assert fv1.checksum != fv2.checksum


class TestVersionDataFrame:
    """Tests for DataFrame versioning utilities."""

    def test_version_dataframe(self):
        """Test attaching versions to DataFrame."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="RSI",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        versioned_df = version_dataframe(df, {"rsi": fv})

        assert "feature_versions" in versioned_df.attrs
        assert "rsi" in versioned_df.attrs["feature_versions"]

    def test_get_feature_versions(self):
        """Test extracting versions from DataFrame."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="RSI",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        versioned_df = version_dataframe(df, {"rsi": fv})
        versions = get_feature_versions(versioned_df)

        assert "rsi" in versions
        assert versions["rsi"]["version"] == "1.0.0"

    def test_get_feature_versions_empty(self):
        """Test getting versions from unversioned DataFrame."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        versions = get_feature_versions(df)

        assert versions == {}

    def test_validate_feature_versions(self):
        """Test validating feature versions."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="RSI",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        versioned_df = version_dataframe(df, {"rsi": fv})

        # Should validate successfully
        assert validate_feature_versions(versioned_df, {"rsi": "1.0.0"}) is True

    def test_validate_feature_versions_mismatch(self):
        """Test validation fails with mismatched versions."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion(
            name="RSI",
            version="1.0.0",
            description="RSI",
            parameters={"period": 14},
            created_at="2025-10-24T00:00:00",
            checksum="abc123",
        )

        versioned_df = version_dataframe(df, {"rsi": fv})

        # Should fail with wrong version
        assert validate_feature_versions(versioned_df, {"rsi": "2.0.0"}) is False

    def test_validate_feature_versions_missing(self):
        """Test validation fails with missing feature."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        versioned_df = version_dataframe(df, {})

        # Should fail when feature not in versions
        assert validate_feature_versions(versioned_df, {"rsi": "1.0.0"}) is False


class TestFeatureSnapshot:
    """Tests for feature snapshot creation/loading."""

    def test_create_snapshot(self):
        """Test creating a feature snapshot."""
        df = pd.DataFrame({"rsi": [30, 40, 50], "atr": [2.5, 2.8, 3.0]})

        fv_rsi = FeatureVersion(
            "RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123"
        )
        fv_atr = FeatureVersion(
            "ATR", "1.0.0", "ATR", {"period": 14}, "2025-10-24T00:00:00", "def456"
        )

        snapshot = create_feature_snapshot(
            df,
            {"rsi": fv_rsi, "atr": fv_atr},
            "AAPL_2025-10-24",
            {"ticker": "AAPL", "date": "2025-10-24"},
        )

        assert snapshot["snapshot_id"] == "AAPL_2025-10-24"
        assert "feature_data" in snapshot
        assert "feature_versions" in snapshot
        assert "metadata" in snapshot
        assert snapshot["metadata"]["ticker"] == "AAPL"

    def test_load_snapshot(self):
        """Test loading a feature snapshot."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion("RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123")

        snapshot = create_feature_snapshot(df, {"rsi": fv}, "AAPL_2025-10-24", {"ticker": "AAPL"})

        loaded_df, loaded_versions = load_feature_snapshot(snapshot)

        assert len(loaded_df) == 3
        assert "rsi" in loaded_df.columns
        assert "rsi" in loaded_versions
        assert loaded_versions["rsi"].version == "1.0.0"

    def test_snapshot_roundtrip(self):
        """Test creating and loading snapshot preserves data."""
        df = pd.DataFrame({"rsi": [30, 40, 50], "atr": [2.5, 2.8, 3.0]})

        fv_rsi = FeatureVersion(
            "RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123"
        )
        fv_atr = FeatureVersion(
            "ATR", "1.0.0", "ATR", {"period": 14}, "2025-10-24T00:00:00", "def456"
        )

        # Create snapshot
        snapshot = create_feature_snapshot(
            df,
            {"rsi": fv_rsi, "atr": fv_atr},
            "AAPL_2025-10-24",
            {"ticker": "AAPL", "date": "2025-10-24"},
        )

        # Load snapshot
        loaded_df, loaded_versions = load_feature_snapshot(snapshot)

        # Verify data preserved
        assert loaded_df["rsi"].tolist() == [30, 40, 50]
        assert loaded_df["atr"].tolist() == [2.5, 2.8, 3.0]
        assert loaded_versions["rsi"].version == "1.0.0"
        assert loaded_versions["atr"].version == "1.0.0"

    def test_snapshot_with_metadata(self):
        """Test snapshot preserves metadata."""
        df = pd.DataFrame({"rsi": [30, 40, 50]})

        fv = FeatureVersion("RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123")

        metadata = {"ticker": "AAPL", "date": "2025-10-24", "strategy": "drop5"}

        snapshot = create_feature_snapshot(df, {"rsi": fv}, "AAPL_2025-10-24", metadata)

        assert snapshot["metadata"]["ticker"] == "AAPL"
        assert snapshot["metadata"]["date"] == "2025-10-24"
        assert snapshot["metadata"]["strategy"] == "drop5"


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_registry(self):
        """Test operations on empty registry."""
        registry = FeatureVersionRegistry()

        assert registry.list_features() == []

        with pytest.raises(KeyError):
            registry.get("NonExistent")

    def test_version_empty_dataframe(self):
        """Test versioning empty DataFrame."""
        df = pd.DataFrame()

        fv = FeatureVersion("RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123")

        versioned_df = version_dataframe(df, {"rsi": fv})

        # Should not error, just attach metadata
        assert "feature_versions" in versioned_df.attrs

    def test_snapshot_empty_dataframe(self):
        """Test snapshot with empty DataFrame."""
        df = pd.DataFrame()

        fv = FeatureVersion("RSI", "1.0.0", "RSI", {"period": 14}, "2025-10-24T00:00:00", "abc123")

        snapshot = create_feature_snapshot(df, {"rsi": fv}, "test_snapshot")

        assert snapshot["feature_data"] == []

    def test_complex_parameters(self):
        """Test feature with complex parameter types."""
        registry = FeatureVersionRegistry()

        complex_params = {
            "period": 14,
            "threshold": 2.5,
            "enabled": True,
            "columns": ["open", "close"],
            "nested": {"key": "value"},
        }

        fv = registry.register("ComplexFeature", "1.0.0", "Complex", complex_params)

        assert fv.parameters["period"] == 14
        assert fv.parameters["nested"]["key"] == "value"
