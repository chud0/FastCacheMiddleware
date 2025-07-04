import re
from typing import Optional, Tuple, TypeAlias, Union

from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import StorageError
from fast_cache_middleware.serializers import BaseSerializer, JSONSerializer, Metadata

StoredResponse: TypeAlias = Tuple[Response, Request, Metadata]


class BaseStorage:
    """Base class for cache storage.

    Args:
        serializer: Serializer for converting Response/Request to string/bytes
        ttl: Cache lifetime in seconds. None for permanent storage
    """

    def __init__(
        self,
        serializer: Optional[BaseSerializer] = None,
        ttl: Optional[Union[int, float]] = None,
    ) -> None:
        self._serializer = serializer or JSONSerializer()

        if ttl is not None and ttl <= 0:
            raise StorageError("TTL must be positive")

        self._ttl = ttl

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        raise NotImplementedError()

    async def retrieve(self, key: str) -> Optional[StoredResponse]:
        raise NotImplementedError()

    async def remove(self, path: re.Pattern) -> None:
        raise NotImplementedError()

    async def close(self) -> None:
        raise NotImplementedError()
