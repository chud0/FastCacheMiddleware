import http
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import is_async_callable

from ._helpers import generate_key
from .exceptions import FastCacheMiddlewareError
from .schemas import CacheConfiguration
from .storages import BaseStorage

logger = logging.getLogger(__name__)

KNOWN_HTTP_METHODS = [method.value for method in http.HTTPMethod]


class CacheControlDirectives(BaseModel):
    no_cache: bool = Field(default=False, alias="no-cache")
    no_store: bool = Field(default=False, alias="no-store")
    private: bool = Field(default=False, alias="private")
    max_age: int | None = Field(default=None, alias="max-age")
    s_maxage: int | None = Field(default=None, alias="s-maxage")
    only_if_cached: bool = Field(default=False, alias="only-if-cached")
    no_transform: bool = Field(default=False, alias="no-transform")


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
        cache_control = request.headers.get("cache-control", "").lower()
        cc = self._parse_cache_control(cache_control)

        if cc.no_store or cc.no_cache or cc.private or cc.max_age == 0:
            return False

        return True

    def _parse_cache_control(self, header: str) -> CacheControlDirectives:
        """
        Parse Cache-Control header into directives.

        Example:
            "max-age=60, no-cache, private"
            ->
            {
                "max-age": 60,
                "no-cache": True,
                "private": True
            }
        """
        directives: dict[str, str | int | bool | None] = {}

        if not header:
            return CacheControlDirectives()

        for part in header.split(","):
            part = part.strip()
            if not part:
                continue

            if "=" in part:
                key, value = part.split("=", 1)
                key = key.lower()
                value = value.strip().strip('"')

                # numeric directives
                if key in {"max-age", "s-maxage", "min-fresh"}:
                    try:
                        directives[key] = int(value)
                    except ValueError:
                        continue
                else:
                    directives[key] = value
            else:
                directives[part.lower()] = True

        return CacheControlDirectives.model_validate(directives)

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
        self, request: Request, cache_configuration: CacheConfiguration
    ) -> str:
        if cache_configuration.key_func:
            kf = cache_configuration.key_func

            if is_async_callable(kf):
                return await kf(request)  # type: ignore[no-any-return]
            return await run_in_threadpool(kf, request)  # type: ignore[arg-type]

        return generate_key(request)

    async def cache_response(
        self,
        cache_key: str,
        request: Request,
        response: Response,
        storage: BaseStorage,
        ttl: Optional[int] = None,
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

            try:
                await storage.set(cache_key, response, request, {"ttl": ttl})
            except FastCacheMiddlewareError as e:
                logger.error("Failed to cache response: %s", e)

        else:
            logger.debug("Skip caching for response: %s", response.status_code)

    async def get_cached_response(
        self, cache_key: str, storage: BaseStorage
    ) -> Response | None:
        """Gets cached response if it exists and is valid.

        Args:
            cache_key: Cache key
            storage: Cache storage

        Returns:
            Response or None if cache is invalid/missing
        """

        try:
            result = await storage.get(cache_key)
        except FastCacheMiddlewareError as e:
            logger.error("Couldn't get the cache: %s", e)
            return None

        if result is None:
            return None

        response, _, _ = result
        return response

    async def invalidate_cache(
        self,
        invalidate_paths: list[re.Pattern],
        storage: BaseStorage,
    ) -> None:
        """Invalidates cache by configuration.

        Args:
            invalidate_paths: List of regex patterns for cache invalidation
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
        for path in invalidate_paths:
            await storage.delete(path)
            logger.info("Invalidated cache for pattern: %s", path.pattern)
