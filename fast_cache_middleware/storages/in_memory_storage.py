import logging
import re
import time
from collections import OrderedDict
from typing import Dict, Optional, Union

from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import (
    NotFoundStorageError,
    StorageError,
    TTLExpiredStorageError,
)
from fast_cache_middleware.serializers import BaseSerializer, Metadata

from .base_storage import BaseStorage, StoredResponse

logger = logging.getLogger(__name__)


class InMemoryStorage(BaseStorage):
    """In-memory cache storage with TTL and LRU eviction support.

    Implements optimized storage of cached responses in memory with:
    - LRU (Least Recently Used) eviction when max_size is exceeded
    - TTL (Time To Live) with lazy checking on read
    - Batch cleanup for better performance

    Args:
        max_size: Maximum number of cache entries
        serializer: Serializer not used for InMemoryStorage
        ttl: Cache lifetime in seconds. None for permanent storage
    """

    def __init__(
        self,
        max_size: int = 1000,
        serializer: Optional[BaseSerializer] = None,
        ttl: Optional[Union[int, float]] = None,
    ) -> None:
        super().__init__(serializer=serializer, ttl=ttl)

        if max_size <= 0:
            raise StorageError("Max size must be positive")

        self._max_size = max_size
        # Cleanup batch size - default 10% of max_size, minimum 1
        self._cleanup_batch_size = max(1, max_size // 10)
        # Cleanup threshold - 5% more than max_size
        self._cleanup_threshold = max_size + max(1, max_size // 20)

        # OrderedDict for efficient LRU
        self._storage: OrderedDict[str, StoredResponse] = OrderedDict()
        # Separate expiry time storage for fast TTL checking
        self._expiry_times: Dict[str, float] = {}
        self._last_expiry_check_time: float = 0
        self._expiry_check_interval: float = 60

    async def set(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        """Saves response to cache with TTL and LRU eviction support.

        If element already exists, it moves to the end (most recently used).
        When size limit is exceeded, batch cleanup of old elements starts.

        Args:
            key: Key for saving
            response: HTTP response to cache
            request: Original HTTP request
            metadata: Cache metadata
        """
        current_time = time.time()

        # Update metadata
        metadata = metadata.copy()
        metadata["write_time"] = current_time

        # If element already exists, remove it (it will be added to the end)
        if key in self._storage:
            logger.info("Element %s removed from cache - overwrite", key)
            self._pop_item(key)

        try:
            self._storage[key] = (response, request, metadata)
        except Exception as e:
            raise StorageError(e)

        data_ttl = metadata.get("ttl", self._ttl)
        if data_ttl is not None:
            self._expiry_times[key] = current_time + data_ttl

        self._remove_expired_items()

        self._cleanup_lru_items()

    async def get(self, key: str) -> Optional[StoredResponse]:
        """Gets response from cache with lazy TTL checking.

        Element moves to the end to update LRU position.
        Expired elements are automatically removed.

        Args:
            key: Key to search

        Returns:
            Tuple (response, request, metadata) if found and not expired, None if not found or expired
        """
        if key not in self._storage:
            raise NotFoundStorageError(key)

        # Lazy TTL check
        if self._is_expired(key):
            self._pop_item(key)
            raise TTLExpiredStorageError(key)

        self._storage.move_to_end(key)

        try:
            cache = self._storage[key]
        except Exception as e:
            raise StorageError(e)

        return cache

    async def delete(self, path: re.Pattern) -> None:
        """Removes responses from cache by request path pattern.

        Args:
            path: Regular expression for matching request paths
        """
        # Find all keys matching path pattern
        keys_to_remove = []
        for key, (_, request, _) in self._storage.items():
            if path.match(request.url.path):
                keys_to_remove.append(key)

        # Remove found keys
        for key in keys_to_remove:
            self._pop_item(key)

        logger.debug(
            "Removed %d entries from cache by pattern %s",
            len(keys_to_remove),
            path.pattern,
        )

    async def close(self) -> None:
        """Clears storage and frees resources."""
        self._storage.clear()
        self._expiry_times.clear()
        logger.debug("Cache storage cleared")

    def __len__(self) -> int:
        """Returns current number of elements in cache."""
        return len(self._storage)

    def _pop_item(self, key: str) -> StoredResponse | None:
        """Removes element from storage and expiry times.

        Args:
            key: Element key to remove
        """
        self._expiry_times.pop(key, None)
        return self._storage.pop(key, None)

    def _is_expired(self, key: str) -> bool:
        """Checks if element is expired by TTL."""
        try:
            return time.time() > self._expiry_times[key]
        except KeyError:
            return False

    def _remove_expired_items(self) -> None:
        """Removes all expired elements from cache."""
        current_time = time.time()

        if current_time - self._last_expiry_check_time < self._expiry_check_interval:
            return

        self._last_expiry_check_time = current_time

        expired_keys = [
            key
            for key, expiry_time in self._expiry_times.items()
            if current_time > expiry_time
        ]
        if not expired_keys:
            return

        for key in expired_keys:
            self._pop_item(key)

        logger.debug("Removed %d expired elements from cache", len(expired_keys))

    def _cleanup_lru_items(self) -> None:
        """Removes old elements by LRU strategy when limit is exceeded."""
        if len(self._storage) <= self._cleanup_threshold:
            return

        # Remove elements in batches for better performance
        items_to_remove = min(
            self._cleanup_batch_size, len(self._storage) - self._max_size
        )

        for _ in range(items_to_remove):
            key, _ = self._storage.popitem(last=False)  # FIFO
            self._expiry_times.pop(key, None)

        logger.debug("Removed %d elements from cache by LRU strategy", items_to_remove)
