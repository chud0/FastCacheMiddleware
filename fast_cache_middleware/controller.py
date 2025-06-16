import http
import logging
import typing as tp
from hashlib import blake2b

from starlette.requests import Request
from starlette.responses import Response

from .depends import CacheConfig, CacheDropConfig
from .storages import BaseStorage

logger = logging.getLogger(__name__)

KNOWN_HTTP_METHODS = [method.value for method in http.HTTPMethod]


def generate_key(request: Request) -> str:
    """Generates fast unique key for caching HTTP request.

    Args:
        request: Starlette Request object.

    Returns:
        str: Unique key for caching, based on request method and path.
        Uses fast blake2b hashing algorithm.

    Note:
        Does not consider scheme and host, as requests usually go to the same host.
        Only considers method, path and query parameters for maximum performance.
    """
    # Get only necessary components from scope
    scope = request.scope
    url = scope["path"]
    if scope["query_string"]:
        url += f"?{scope['query_string'].decode('ascii')}"

    # Use fast blake2b algorithm with minimal digest size
    key = blake2b(digest_size=8)
    key.update(request.method.encode())
    key.update(url.encode())

    return key.hexdigest()


class Controller:
    """Caching controller for Starlette/FastAPI.

    Responsibilities:
    1. Define rules for caching requests and responses
    2. Generate cache keys with custom functions
    3. Manage TTL and validation of cached data
    4. Check HTTP caching headers
    5. Invalidate cache by URL patterns

    Supports:
    - Custom key generation functions via CacheConfig
    - Cache invalidation by URL patterns via CacheDropConfig
    - Standard HTTP caching headers (Cache-Control, ETag, Last-Modified)
    - Cache lifetime configuration via max_age in CacheConfig
    """

    def __init__(
        self,
        cacheable_methods: list[str] | None = None,
        cacheable_status_codes: list[int] | None = None,
    ) -> None:
        self.cacheable_methods = []
        if cacheable_methods:
            for method in cacheable_methods:
                method = method.upper()
                if method in KNOWN_HTTP_METHODS:
                    self.cacheable_methods.append(method)
                else:
                    raise ValueError(f"Invalid HTTP method: {method}")
        else:
            self.cacheable_methods.append(http.HTTPMethod.GET.value)

        self.cacheable_status_codes = cacheable_status_codes or [
            http.HTTPStatus.OK.value,
            http.HTTPStatus.MOVED_PERMANENTLY.value,
            http.HTTPStatus.PERMANENT_REDIRECT.value,
        ]

    async def is_cachable_request(self, request: Request) -> bool:
        """Determines if this request should be cached.

        Args:
            request: HTTP request
            cache_config: Cache configuration

        Returns:
            bool: True if request should be cached
        """
        # Cache only GET requests by default
        if request.method not in self.cacheable_methods:
            return False

        # Check Cache-Control headers
        # todo: add parsing cache-control function
        cache_control = request.headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False

        return True

    async def is_cachable_response(self, response: Response) -> bool:
        """Determines if this response can be cached.

        Args:
            request: HTTP request
            response: HTTP response

        Returns:
            bool: True if response can be cached
        """
        if response.status_code not in self.cacheable_status_codes:
            return False

        # Check Cache-Control headers
        cache_control = response.headers.get("cache-control", "").lower()
        if (
            "no-cache" in cache_control
            or "no-store" in cache_control
            or "private" in cache_control
        ):
            return False

        # Check response size (don't cache too large responses)
        if (
            hasattr(response, "body")
            and response.body
            and len(response.body) > 1024 * 1024
        ):  # 1MB
            return False

        return True

    async def generate_cache_key(
        self, request: Request, cache_config: CacheConfig
    ) -> str:
        """Generates cache key for request.

        Args:
            request: HTTP request
            cache_config: Cache configuration

        Returns:
            str: Cache key
        """
        # Use custom key generation function if available
        if cache_config.key_func:
            return cache_config.key_func(request)

        # Use standard function
        return generate_key(request)

    async def cache_response(
        self,
        cache_key: str,
        request: Request,
        response: Response,
        storage: BaseStorage,
        ttl: tp.Optional[int] = None,
    ) -> None:
        """Saves response to cache.

        Args:
            cache_key: Cache key
            request: HTTP request
            response: HTTP response to cache
            storage: Cache storage
            ttl: Cache lifetime in seconds
        todo: in meta can write etag and last_modified from response headers
        """
        if await self.is_cachable_response(response):
            response.headers["X-Cache-Status"] = "HIT"
            await storage.store(cache_key, response, request, {"ttl": ttl})
        else:
            logger.debug("Skip caching for response: %s", response.status_code)

    async def get_cached_response(
        self, cache_key: str, storage: BaseStorage
    ) -> tp.Optional[Response]:
        """Gets cached response if it exists and is valid.

        Args:
            cache_key: Cache key
            storage: Cache storage

        Returns:
            Response or None if cache is invalid/missing
        """
        result = await storage.retrieve(cache_key)
        if result is None:
            return None
        response, _, _ = result
        return response

    async def invalidate_cache(
        self,
        cache_drop_config: CacheDropConfig,
        storage: BaseStorage,
    ) -> None:
        """Invalidates cache by configuration.

        Args:
            cache_drop_config: Cache invalidation configuration
            storage: Cache storage

        TODO: Comments on improvements:

        1. Need to add pattern support in storage for bulk invalidation
           by key prefix/mask (especially for Redis/Memcached)

        2. Desirable to add bulk operations for removing multiple keys
           in one storage request

        3. Can add delayed/asynchronous invalidation via queue
           for large datasets

        4. Should add invalidation strategies:
           - Immediate (current implementation)
           - Delayed (via TTL)
           - Partial (only specific fields)

        5. Add tag support for grouping related caches
           and their joint invalidation
        """
        for path in cache_drop_config.paths:
            await storage.remove(path)
            logger.info("Invalidated cache for pattern: %s", path.pattern)
