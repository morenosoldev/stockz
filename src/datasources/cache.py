"""File-based caching system for data adapters.

This module provides a simple but effective file-based cache with TTL support,
compression, and proper key generation for caching expensive API calls.

The cache is designed to:
- Reduce API calls and associated costs
- Speed up development and testing
- Maintain reproducibility with versioned cache entries
- Support graceful degradation when cache is unavailable
"""

import hashlib
import json
import pickle
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from src.ops.logging import get_logger

logger = get_logger(__name__)


class CacheError(Exception):
    """Exception raised when cache operations fail."""

    pass


class Cache:
    """File-based cache with TTL support.

    Stores cached data in JSON or pickle format with automatic TTL expiration.

    Attributes:
        cache_dir: Directory path for cache storage
        ttl_seconds: Default time-to-live in seconds
        use_compression: Whether to use gzip compression (not implemented yet)

    Example:
        >>> cache = Cache(cache_dir="/tmp/cache", ttl_seconds=3600)
        >>> cache.set("my_key", {"data": "value"})
        >>> data = cache.get("my_key")
        >>> data["data"]
        'value'
    """

    def __init__(
        self,
        cache_dir: str | Path = "data/cache",
        ttl_seconds: int = 3600,
        use_compression: bool = False,
    ):
        """Initialize cache.

        Args:
            cache_dir: Directory for cache files (created if doesn't exist)
            ttl_seconds: Default TTL in seconds (0 = no expiration)
            use_compression: Whether to compress cached data (future feature)
        """
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_seconds
        self.use_compression = use_compression
        self.logger = get_logger(f"{__name__}.Cache")

        # Create cache directory if it doesn't exist
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Cache directory initialized", cache_dir=str(self.cache_dir))
        except OSError as e:
            self.logger.error(
                "Failed to create cache directory",
                cache_dir=str(self.cache_dir),
                error=str(e),
            )
            raise CacheError(f"Failed to create cache directory: {e}") from e

    def _generate_cache_key(self, key: str | dict[str, Any]) -> str:
        """Generate a filesystem-safe cache key.

        Args:
            key: Cache key (string or dict)

        Returns:
            SHA256 hash of the key for use as filename

        Example:
            >>> cache = Cache()
            >>> key = cache._generate_cache_key("my_key")
            >>> len(key)
            64
        """
        if isinstance(key, dict):
            # Sort dict keys for consistent hashing
            key_str = json.dumps(key, sort_keys=True)
        else:
            key_str = str(key)

        # Generate SHA256 hash
        hash_obj = hashlib.sha256(key_str.encode("utf-8"))
        return hash_obj.hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get the file path for a cache key.

        Args:
            cache_key: Hashed cache key

        Returns:
            Path to cache file
        """
        return self.cache_dir / f"{cache_key}.cache"

    def _get_metadata_path(self, cache_key: str) -> Path:
        """Get the file path for cache metadata.

        Args:
            cache_key: Hashed cache key

        Returns:
            Path to metadata file
        """
        return self.cache_dir / f"{cache_key}.meta"

    def set(
        self,
        key: str | dict[str, Any],
        data: Any,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Store data in cache.

        Args:
            key: Cache key (string or dict for composite keys)
            data: Data to cache (must be JSON-serializable or pickleable)
            ttl_seconds: TTL in seconds (None = use default, 0 = no expiration)
            metadata: Optional metadata to store with cached data

        Returns:
            True if successful, False otherwise

        Example:
            >>> cache = Cache()
            >>> cache.set("prices:AAPL", {"price": 150.0}, ttl_seconds=300)
            True
        """
        cache_key = self._generate_cache_key(key)
        cache_path = self._get_cache_path(cache_key)
        meta_path = self._get_metadata_path(cache_key)

        # Use default TTL if not specified
        if ttl_seconds is None:
            ttl_seconds = self.ttl_seconds

        # Calculate expiration time
        if ttl_seconds > 0:
            expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        else:
            expires_at = None  # No expiration

        try:
            # Try JSON first (human-readable, debuggable)
            try:
                with open(cache_path, "w") as f:
                    json.dump(data, f, indent=2)
                serialization_method = "json"
            except (TypeError, ValueError):
                # Fall back to pickle for non-JSON-serializable objects
                with open(cache_path, "wb") as f:
                    pickle.dump(data, f)
                serialization_method = "pickle"

            # Store metadata
            meta = {
                "key": str(key),
                "created_at": datetime.now(UTC).isoformat(),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "ttl_seconds": ttl_seconds,
                "serialization": serialization_method,
                "metadata": metadata or {},
            }
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)

            self.logger.debug(
                "Cache set",
                key=str(key),
                cache_key=cache_key,
                ttl_seconds=ttl_seconds,
                serialization=serialization_method,
            )
            return True

        except (OSError, pickle.PickleError) as e:
            self.logger.error(
                "Failed to set cache",
                key=str(key),
                cache_key=cache_key,
                error=str(e),
            )
            return False

    def get(self, key: str | dict[str, Any]) -> Any | None:
        """Retrieve data from cache.

        Args:
            key: Cache key (string or dict)

        Returns:
            Cached data if found and not expired, None otherwise

        Example:
            >>> cache = Cache()
            >>> cache.set("my_key", {"value": 42})
            True
            >>> data = cache.get("my_key")
            >>> data["value"]
            42
        """
        cache_key = self._generate_cache_key(key)
        cache_path = self._get_cache_path(cache_key)
        meta_path = self._get_metadata_path(cache_key)

        # Check if cache file exists
        if not cache_path.exists():
            self.logger.debug("Cache miss - file not found", key=str(key), cache_key=cache_key)
            return None

        try:
            # Load metadata
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)

                # Check expiration
                expires_at_str = meta.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    now = datetime.now(UTC)
                    # Normalize to naive UTC for comparison
                    expires_naive = (
                        expires_at.replace(tzinfo=None)
                        if expires_at.tzinfo is not None
                        else expires_at
                    )
                    now_naive = now.replace(tzinfo=None)
                    if expires_naive < now_naive:
                        self.logger.debug(
                            "Cache miss - expired",
                            key=str(key),
                            cache_key=cache_key,
                            expires_at=expires_at_str,
                        )
                        # Clean up expired cache
                        self.delete(key)
                        return None

                serialization_method = meta.get("serialization", "json")
            else:
                # Assume JSON if metadata missing
                serialization_method = "json"

            # Load cached data
            if serialization_method == "json":
                with open(cache_path) as f:
                    data = json.load(f)
            else:
                with open(cache_path, "rb") as f:
                    data = pickle.load(f)

            self.logger.debug(
                "Cache hit",
                key=str(key),
                cache_key=cache_key,
                serialization=serialization_method,
            )
            return data

        except (OSError, json.JSONDecodeError, pickle.PickleError) as e:
            self.logger.error(
                "Failed to get cache",
                key=str(key),
                cache_key=cache_key,
                error=str(e),
            )
            return None

    def delete(self, key: str | dict[str, Any]) -> bool:
        """Delete cached data.

        Args:
            key: Cache key (string or dict)

        Returns:
            True if deleted, False if not found or error

        Example:
            >>> cache = Cache()
            >>> cache.set("temp_key", "data")
            True
            >>> cache.delete("temp_key")
            True
        """
        cache_key = self._generate_cache_key(key)
        cache_path = self._get_cache_path(cache_key)
        meta_path = self._get_metadata_path(cache_key)

        deleted = False
        try:
            if cache_path.exists():
                cache_path.unlink()
                deleted = True
            if meta_path.exists():
                meta_path.unlink()

            if deleted:
                self.logger.debug("Cache deleted", key=str(key), cache_key=cache_key)
            return deleted

        except OSError as e:
            self.logger.error(
                "Failed to delete cache",
                key=str(key),
                cache_key=cache_key,
                error=str(e),
            )
            return False

    def clear(self) -> int:
        """Clear all cached data.

        Returns:
            Number of cache entries deleted

        Example:
            >>> cache = Cache()
            >>> cache.set("key1", "data1")
            True
            >>> cache.set("key2", "data2")
            True
            >>> cache.clear()
            2
        """
        count = 0
        try:
            for cache_file in self.cache_dir.glob("*.cache"):
                cache_file.unlink()
                count += 1

            for meta_file in self.cache_dir.glob("*.meta"):
                meta_file.unlink()

            self.logger.info("Cache cleared", entries_deleted=count)
            return count

        except OSError as e:
            self.logger.error("Failed to clear cache", error=str(e))
            raise CacheError(f"Failed to clear cache: {e}") from e

    def get_metadata(self, key: str | dict[str, Any]) -> dict[str, Any] | None:
        """Get metadata for cached entry.

        Args:
            key: Cache key (string or dict)

        Returns:
            Metadata dict if found, None otherwise

        Example:
            >>> cache = Cache()
            >>> cache.set("my_key", "data", metadata={"source": "api"})
            True
            >>> meta = cache.get_metadata("my_key")
            >>> meta["metadata"]["source"]
            'api'
        """
        cache_key = self._generate_cache_key(key)
        meta_path = self._get_metadata_path(cache_key)

        if not meta_path.exists():
            return None

        try:
            with open(meta_path) as f:
                metadata: dict[str, Any] = json.load(f)
                return metadata
        except (OSError, json.JSONDecodeError) as e:
            self.logger.error(
                "Failed to get metadata",
                key=str(key),
                cache_key=cache_key,
                error=str(e),
            )
            return None

    def cleanup_expired(self) -> int:
        """Remove all expired cache entries.

        Returns:
            Number of expired entries removed

        Example:
            >>> cache = Cache()
            >>> cache.set("temp", "data", ttl_seconds=1)
            True
            >>> time.sleep(2)
            >>> cache.cleanup_expired()
            1
        """
        count = 0
        now = datetime.now(UTC)

        for meta_file in self.cache_dir.glob("*.meta"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)

                expires_at_str = meta.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    # Normalize to naive UTC for comparison
                    expires_naive = (
                        expires_at.replace(tzinfo=None)
                        if expires_at.tzinfo is not None
                        else expires_at
                    )
                    now_naive = now.replace(tzinfo=None)
                    if expires_naive < now_naive:
                        # Delete expired cache
                        cache_key = meta_file.stem
                        cache_file = self.cache_dir / f"{cache_key}.cache"
                        if cache_file.exists():
                            cache_file.unlink()
                        meta_file.unlink()
                        count += 1

            except (OSError, json.JSONDecodeError, ValueError) as e:
                self.logger.warning(
                    "Failed to process metadata during cleanup",
                    meta_file=str(meta_file),
                    error=str(e),
                )

        if count > 0:
            self.logger.info("Cleaned up expired cache entries", count=count)

        return count

    def get_size(self) -> int:
        """Get total size of cache directory in bytes.

        Returns:
            Total cache size in bytes

        Example:
            >>> cache = Cache()
            >>> cache.set("key", "data")
            True
            >>> size = cache.get_size()
            >>> size > 0
            True
        """
        total_size = 0
        for file_path in self.cache_dir.rglob("*"):
            if file_path.is_file():
                total_size += file_path.stat().st_size
        return total_size

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache stats (entries, size, expired)

        Example:
            >>> cache = Cache()
            >>> cache.set("key1", "data1")
            True
            >>> stats = cache.get_stats()
            >>> stats["total_entries"]
            1
        """
        total_entries = len(list(self.cache_dir.glob("*.cache")))
        total_size = self.get_size()

        # Count expired entries
        expired_count = 0
        now = datetime.now(UTC)
        for meta_file in self.cache_dir.glob("*.meta"):
            try:
                with open(meta_file) as f:
                    meta = json.load(f)
                expires_at_str = meta.get("expires_at")
                if expires_at_str:
                    expires_at = datetime.fromisoformat(expires_at_str)
                    # Normalize to naive UTC for comparison
                    expires_naive = (
                        expires_at.replace(tzinfo=None)
                        if expires_at.tzinfo is not None
                        else expires_at
                    )
                    now_naive = now.replace(tzinfo=None)
                    if expires_naive < now_naive:
                        expired_count += 1
            except (OSError, json.JSONDecodeError, ValueError):
                pass

        return {
            "cache_dir": str(self.cache_dir),
            "total_entries": total_entries,
            "expired_entries": expired_count,
            "total_size_bytes": total_size,
            "ttl_seconds": self.ttl_seconds,
        }
