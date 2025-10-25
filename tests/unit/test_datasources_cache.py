"""Tests for cache system."""

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.datasources.cache import Cache


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create a temporary cache directory."""
    cache_dir = tmp_path / "test_cache"
    yield cache_dir
    # Cleanup is automatic with tmp_path


@pytest.fixture
def cache(temp_cache_dir):
    """Create a Cache instance with temporary directory."""
    return Cache(cache_dir=temp_cache_dir, ttl_seconds=3600)


class TestCacheInitialization:
    """Test Cache initialization."""

    def test_create_cache_default_dir(self, tmp_path, monkeypatch):
        """Test creating cache with default directory."""
        # Change to temp directory to avoid polluting workspace
        monkeypatch.chdir(tmp_path)
        cache = Cache()
        assert cache.cache_dir == Path("data/cache")
        assert cache.ttl_seconds == 3600
        assert cache.use_compression is False

    def test_create_cache_custom_dir(self, temp_cache_dir):
        """Test creating cache with custom directory."""
        cache = Cache(cache_dir=temp_cache_dir, ttl_seconds=7200)
        assert cache.cache_dir == temp_cache_dir
        assert cache.ttl_seconds == 7200

    def test_cache_dir_created(self, temp_cache_dir):
        """Test cache directory is created if doesn't exist."""
        assert not temp_cache_dir.exists()
        Cache(cache_dir=temp_cache_dir)
        assert temp_cache_dir.exists()
        assert temp_cache_dir.is_dir()

    def test_cache_dir_already_exists(self, temp_cache_dir):
        """Test cache works if directory already exists."""
        temp_cache_dir.mkdir(parents=True)
        cache = Cache(cache_dir=temp_cache_dir)
        assert cache.cache_dir.exists()


class TestCacheKeyGeneration:
    """Test cache key generation."""

    def test_generate_key_from_string(self, cache):
        """Test generating cache key from string."""
        key = cache._generate_cache_key("test_key")
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hash

    def test_generate_key_from_dict(self, cache):
        """Test generating cache key from dict."""
        key = cache._generate_cache_key({"ticker": "AAPL", "date": "2025-10-24"})
        assert isinstance(key, str)
        assert len(key) == 64

    def test_key_consistency(self, cache):
        """Test same input produces same key."""
        key1 = cache._generate_cache_key("test")
        key2 = cache._generate_cache_key("test")
        assert key1 == key2

    def test_dict_key_order_independence(self, cache):
        """Test dict key order doesn't affect hash."""
        key1 = cache._generate_cache_key({"a": 1, "b": 2})
        key2 = cache._generate_cache_key({"b": 2, "a": 1})
        assert key1 == key2

    def test_different_keys_produce_different_hashes(self, cache):
        """Test different inputs produce different hashes."""
        key1 = cache._generate_cache_key("test1")
        key2 = cache._generate_cache_key("test2")
        assert key1 != key2


class TestCacheSetGet:
    """Test cache set and get operations."""

    def test_set_and_get_json_data(self, cache):
        """Test setting and getting JSON-serializable data."""
        data = {"price": 150.0, "volume": 1000000}
        assert cache.set("test_key", data)

        retrieved = cache.get("test_key")
        assert retrieved == data

    def test_set_and_get_pickle_data(self, cache):
        """Test setting and getting non-JSON data (pickled)."""
        # Use a built-in type that isn't JSON-serializable directly
        import datetime as dt

        data = dt.timedelta(days=5, hours=3, minutes=30)
        assert cache.set("test_key", data)

        retrieved = cache.get("test_key")
        assert isinstance(retrieved, dt.timedelta)
        assert retrieved == data

    def test_get_nonexistent_key(self, cache):
        """Test getting nonexistent key returns None."""
        assert cache.get("nonexistent") is None

    def test_set_with_dict_key(self, cache):
        """Test set/get with composite dict key."""
        key = {"ticker": "AAPL", "date": "2025-10-24"}
        data = {"price": 150.0}

        assert cache.set(key, data)
        retrieved = cache.get(key)
        assert retrieved == data

    def test_set_with_custom_ttl(self, cache):
        """Test set with custom TTL."""
        assert cache.set("test_key", "data", ttl_seconds=10)

        # Check metadata
        meta = cache.get_metadata("test_key")
        assert meta is not None
        assert meta["ttl_seconds"] == 10

    def test_set_with_metadata(self, cache):
        """Test set with custom metadata."""
        assert cache.set("test_key", "data", metadata={"source": "api"})

        meta = cache.get_metadata("test_key")
        assert meta is not None
        assert meta["metadata"]["source"] == "api"


class TestCacheTTL:
    """Test cache TTL expiration."""

    def test_expired_cache_returns_none(self, cache):
        """Test expired cache entry returns None."""
        # Set with 1 second TTL
        cache.set("test_key", "data", ttl_seconds=1)

        # Wait for expiration
        time.sleep(1.5)

        # Should return None
        assert cache.get("test_key") is None

    def test_expired_cache_deleted(self, cache):
        """Test expired cache files are deleted on get."""
        cache.set("test_key", "data", ttl_seconds=1)

        # Get cache key to check files
        cache_key = cache._generate_cache_key("test_key")
        cache_path = cache._get_cache_path(cache_key)
        meta_path = cache._get_metadata_path(cache_key)

        # Files should exist initially
        assert cache_path.exists()
        assert meta_path.exists()

        # Wait for expiration
        time.sleep(1.5)

        # Get should clean up files
        cache.get("test_key")

        # Files should be deleted
        assert not cache_path.exists()
        assert not meta_path.exists()

    def test_zero_ttl_no_expiration(self, cache):
        """Test TTL=0 means no expiration."""
        cache.set("test_key", "data", ttl_seconds=0)

        meta = cache.get_metadata("test_key")
        assert meta is not None
        assert meta["expires_at"] is None

        # Should still be retrievable
        assert cache.get("test_key") == "data"

    def test_unexpired_cache_accessible(self, cache):
        """Test unexpired cache is accessible."""
        cache.set("test_key", "data", ttl_seconds=10)

        # Should be accessible immediately
        assert cache.get("test_key") == "data"

        # Should still be accessible after short delay
        time.sleep(0.5)
        assert cache.get("test_key") == "data"


class TestCacheDelete:
    """Test cache deletion."""

    def test_delete_existing(self, cache):
        """Test deleting existing cache entry."""
        cache.set("test_key", "data")
        assert cache.delete("test_key") is True
        assert cache.get("test_key") is None

    def test_delete_nonexistent(self, cache):
        """Test deleting nonexistent key returns False."""
        assert cache.delete("nonexistent") is False

    def test_delete_removes_files(self, cache):
        """Test delete removes both cache and metadata files."""
        cache.set("test_key", "data")

        cache_key = cache._generate_cache_key("test_key")
        cache_path = cache._get_cache_path(cache_key)
        meta_path = cache._get_metadata_path(cache_key)

        assert cache_path.exists()
        assert meta_path.exists()

        cache.delete("test_key")

        assert not cache_path.exists()
        assert not meta_path.exists()


class TestCacheClear:
    """Test cache clear operation."""

    def test_clear_empty_cache(self, cache):
        """Test clearing empty cache."""
        count = cache.clear()
        assert count == 0

    def test_clear_with_entries(self, cache):
        """Test clearing cache with entries."""
        cache.set("key1", "data1")
        cache.set("key2", "data2")
        cache.set("key3", "data3")

        count = cache.clear()
        assert count == 3

        # All entries should be gone
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.get("key3") is None

    def test_clear_removes_all_files(self, cache):
        """Test clear removes all cache and metadata files."""
        cache.set("key1", "data1")
        cache.set("key2", "data2")

        cache.clear()

        # No .cache or .meta files should remain
        assert len(list(cache.cache_dir.glob("*.cache"))) == 0
        assert len(list(cache.cache_dir.glob("*.meta"))) == 0


class TestCacheMetadata:
    """Test cache metadata operations."""

    def test_get_metadata_existing(self, cache):
        """Test getting metadata for existing entry."""
        cache.set("test_key", "data", metadata={"source": "api"})

        meta = cache.get_metadata("test_key")
        assert meta is not None
        assert meta["key"] == "test_key"
        assert meta["ttl_seconds"] == 3600
        assert meta["serialization"] == "json"
        assert meta["metadata"]["source"] == "api"
        assert "created_at" in meta
        assert "expires_at" in meta

    def test_get_metadata_nonexistent(self, cache):
        """Test getting metadata for nonexistent entry."""
        meta = cache.get_metadata("nonexistent")
        assert meta is None

    def test_metadata_timestamps(self, cache):
        """Test metadata contains valid timestamps."""
        before = datetime.now(UTC)
        cache.set("test_key", "data", ttl_seconds=3600)
        after = datetime.now(UTC)

        meta = cache.get_metadata("test_key")
        assert meta is not None

        created_at = datetime.fromisoformat(meta["created_at"])
        expires_at = datetime.fromisoformat(meta["expires_at"])

        # Created at should be between before and after
        assert (
            before.replace(tzinfo=None)
            <= created_at.replace(tzinfo=None)
            <= after.replace(tzinfo=None)
        )

        # Expires at should be ~1 hour later
        delta = (expires_at - created_at).total_seconds()
        assert 3595 <= delta <= 3605  # Allow small variation


class TestCleanupExpired:
    """Test cleanup of expired entries."""

    def test_cleanup_no_expired(self, cache):
        """Test cleanup with no expired entries."""
        cache.set("key1", "data1", ttl_seconds=3600)
        cache.set("key2", "data2", ttl_seconds=3600)

        count = cache.cleanup_expired()
        assert count == 0

        # Entries should still exist
        assert cache.get("key1") == "data1"
        assert cache.get("key2") == "data2"

    def test_cleanup_expired_entries(self, cache):
        """Test cleanup removes expired entries."""
        cache.set("expired", "data", ttl_seconds=1)
        cache.set("valid", "data", ttl_seconds=3600)

        # Wait for expiration
        time.sleep(1.5)

        count = cache.cleanup_expired()
        assert count == 1

        # Expired should be gone
        assert cache.get("expired") is None

        # Valid should remain
        assert cache.get("valid") == "data"

    def test_cleanup_multiple_expired(self, cache):
        """Test cleanup removes multiple expired entries."""
        cache.set("expired1", "data", ttl_seconds=1)
        cache.set("expired2", "data", ttl_seconds=1)
        cache.set("valid", "data", ttl_seconds=3600)

        time.sleep(1.5)

        count = cache.cleanup_expired()
        assert count == 2

        assert cache.get("expired1") is None
        assert cache.get("expired2") is None
        assert cache.get("valid") == "data"


class TestCacheSize:
    """Test cache size calculation."""

    def test_size_empty_cache(self, cache):
        """Test size of empty cache."""
        size = cache.get_size()
        assert size == 0

    def test_size_with_entries(self, cache):
        """Test size with cache entries."""
        cache.set("key1", {"data": "value" * 100})
        cache.set("key2", {"data": "value" * 100})

        size = cache.get_size()
        assert size > 0

    def test_size_includes_metadata(self, cache):
        """Test size includes metadata files."""
        cache.set("test_key", "data")

        cache_key = cache._generate_cache_key("test_key")
        cache_path = cache._get_cache_path(cache_key)
        meta_path = cache._get_metadata_path(cache_key)

        total_size = cache.get_size()
        expected_size = cache_path.stat().st_size + meta_path.stat().st_size

        assert total_size == expected_size


class TestCacheStats:
    """Test cache statistics."""

    def test_stats_empty_cache(self, cache):
        """Test stats for empty cache."""
        stats = cache.get_stats()

        assert stats["total_entries"] == 0
        assert stats["expired_entries"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["ttl_seconds"] == 3600
        assert "cache_dir" in stats

    def test_stats_with_entries(self, cache):
        """Test stats with cache entries."""
        cache.set("key1", "data1")
        cache.set("key2", "data2")

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 0
        assert stats["total_size_bytes"] > 0

    def test_stats_with_expired(self, cache):
        """Test stats count expired entries."""
        cache.set("expired", "data", ttl_seconds=1)
        cache.set("valid", "data", ttl_seconds=3600)

        time.sleep(1.5)

        stats = cache.get_stats()

        assert stats["total_entries"] == 2
        assert stats["expired_entries"] == 1
