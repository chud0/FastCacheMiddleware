import logging
import re
import time
import typing as tp

from redis import Redis
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import StorageError
from fast_cache_middleware.serializers import BaseSerializer, JSONSerializer, Metadata
from .base_storage import BaseStorage, StoredResponse

logger = logging.getLogger(__name__)


class RedisStorage(BaseStorage):
    def __init__(
        self,
        redis_client: Redis,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[tp.Union[int, float]] = None,
        namespace: str = "cache",
    ) -> None:
        super().__init__(serializer, ttl)
        self._serializer = serializer or JSONSerializer()

        if ttl is not None and ttl <= 0:
            raise StorageError("TTL must be positive")

        self._ttl = ttl
        self._storage = redis_client
        self._namespace = namespace

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        """
        Saves response to cache with TTL. Redis automatically remove cache if TTL expired.
        """
        current_time = time.time()

        metadata["write_time"] = current_time

        value = self._serializer.dumps(response, request, metadata)
        logger.debug("Serialized data: %s", value)
        ttl = metadata.get("ttl", self._ttl)
        logger.debug(f"TTL: %s", ttl)

        full_key = self._full_key(key)
        logger.debug(f"Full key: %s", full_key)

        if await self._storage.exists(full_key):
            logger.info("Element %s removed from cache - overwrite", key)
            await self._storage.delete(full_key)

        await self._storage.set(full_key, value, ex=ttl)
        logger.info("Data written to Redis")

    async def retrieve(self, key: str) -> tp.Optional[StoredResponse]:
        """
        Get response from Redis. If TTL expired returns None.
        """
        full_key = self._full_key(key)
        raw_data = await self._storage.get(full_key)

        if raw_data is None:
            logger.debug("Key %s will be removed from Redis - TTL expired", full_key)
            return None

        logger.debug(f"Takin data from Redis: %s", raw_data)
        try:
            return self._serializer.loads(raw_data)
        except Exception as e:
            logger.warning(
                "Failed to deserialize cached response for key %s: %s", key, e
            )
            return None

    async def remove(self, path: re.Pattern) -> None:
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
            logger.warning("The search did not find any matches")
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
