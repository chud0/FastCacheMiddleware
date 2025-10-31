import logging
import re
import time
from typing import Optional, Union

try:
    import redis.asyncio as redis
except ImportError:
    redis = None  # type: ignore

from redis.exceptions import RedisError
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import (
    NotFoundStorageError,
    StorageError,
    TTLExpiredStorageError,
)
from fast_cache_middleware.serializers import BaseSerializer, JSONSerializer, Metadata

from .base_storage import BaseStorage, StoredResponse

logger = logging.getLogger(__name__)


class RedisStorage(BaseStorage):
    def __init__(
        self,
        redis_client: redis.Redis,
        serializer: Optional[BaseSerializer] = None,
        ttl: Optional[Union[int, float]] = None,
        namespace: str = "cache",
    ) -> None:
        if redis is None:
            raise ImportError(
                "Redis is required for RedisStorage. "
                "Install with Redis: fast-cache-middleware[redis]"
            )

        super().__init__(serializer, ttl)
        self._serializer = serializer or JSONSerializer()

        if ttl is not None and ttl <= 0:
            raise StorageError("TTL must be positive")

        self._ttl = ttl
        self._storage = redis_client
        self._namespace = namespace

    async def set(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        """
        Saves response to cache with TTL. Redis automatically remove cache if TTL expired.
        """
        current_time = time.time()

        metadata["write_time"] = current_time

        value = await self._serializer.dumps(response, request, metadata)
        ttl = metadata.get("ttl", self._ttl)
        logger.debug(f"TTL: %s", ttl)

        full_key = self._full_key(key)

        if await self._check_exists(full_key):
            logger.info("Element %s removed from cache - overwrite", key)
            await self._storage.delete(full_key)

        await self._storage.set(full_key, value, ex=ttl)
        logger.info("Data written to Redis, key=%s", full_key)

    async def get(self, key: str) -> StoredResponse:
        """
        Get response from Redis. If TTL expired returns None.
        """
        full_key = self._full_key(key)

        if not await self._check_exists(full_key):
            raise TTLExpiredStorageError(full_key)

        raw_data = await self._storage.get(full_key)

        if raw_data is None:
            raise NotFoundStorageError(key)

        return self._serializer.loads(raw_data)

    async def delete(self, path: re.Pattern) -> None:
        """
        Deleting the cache using the specified path
        """
        raw = path.pattern
        if raw.startswith("^"):
            raw = raw[1:]

        pattern = self._full_key(str(raw.rstrip("$") + "/*"))
        logger.debug(f"Removing key: %s", pattern)

        result = await self._storage.scan(match=pattern)

        if not result[1]:
            logger.warning("A search in the repository did not reveal any matches.")
            return

        logger.debug(f"Result: %s", result[1])
        for value in result[1]:
            await self._storage.delete(value)
            logger.info(f"Key deleted from Redis: %s", value)

    async def close(self) -> None:
        await self._storage.flushdb()
        logger.debug("Cache storage cleared")

    def _full_key(self, key: str) -> str:
        return f"{self._namespace}:{key}"

    async def _check_exists(self, key: str) -> int:
        try:
            return await self._storage.exists(key)
        except RedisError as e:
            raise StorageError(e)
