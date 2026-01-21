import copy
import logging
import re
import typing as tp

from fastapi import routing
from starlette.requests import Request
from starlette.routing import Match, compile_path, get_name
from starlette.types import ASGIApp, Receive, Scope, Send

from fast_cache_middleware._helpers import (
    get_app_routes,
    get_routes,
    set_cache_age_in_openapi_schema,
)
from fast_cache_middleware.controller import Controller
from fast_cache_middleware.depends import (
    BaseCacheConfigDepends,
    CacheConfig,
    CacheDropConfig,
)
from fast_cache_middleware.schemas import CacheConfiguration, RouteInfo
from fast_cache_middleware.storages import BaseStorage, InMemoryStorage

from .base import BaseMiddleware
from .send_wrapper import CacheSendWrapper

logger = logging.getLogger(__name__)


class FastCacheMiddleware(BaseMiddleware):
    """Middleware for caching responses in ASGI applications.

    Route resolution approach:
    1. Analyzes all routes and their dependencies at startup
    2. Finds corresponding route by path and method on request
    3. Extracts cache configuration from route dependencies
    4. Performs standard caching/invalidation logic

    Advantages:
    - Pre-route analysis - fast configuration lookup
    - Support for all FastAPI dependencies
    - Flexible cache management at route level
    - Efficient cache invalidation

    Args:
        app: ASGI application to wrap
        storage: Cache storage (default InMemoryStorage)
        controller: Controller for managing caching logic
    """

    def __init__(
        self,
        app: ASGIApp,
        storage: tp.Optional[BaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        super().__init__(app)

        self.storage = storage or InMemoryStorage()
        self.controller = controller or Controller()
        self._openapi_initialized = False

        self._routes_info: list[RouteInfo] = []

        current_app: tp.Any = app
        while current_app := getattr(current_app, "app", None):
            if isinstance(current_app, routing.APIRouter):
                _routes = get_routes(current_app)
                self._routes_info = self._extract_routes_info(_routes)
                break

    async def on_lifespan(self, scope: Scope, _: Receive, __: Send) -> bool | None:
        app_routes = get_app_routes(scope["app"])
        set_cache_age_in_openapi_schema(scope["app"])
        self._routes_info = self._extract_routes_info(app_routes)
        return None

    async def on_http(self, scope: Scope, receive: Receive, send: Send) -> bool | None:
        request = Request(scope, receive)

        if not self._openapi_initialized:
            set_cache_age_in_openapi_schema(scope["app"])
            self._openapi_initialized = True

        # Find matching route
        route_info = self._find_matching_route(request, self._routes_info)
        if not route_info:
            return None

        cache_configuration = route_info.cache_config

        # Handle invalidation if specified
        if cache_configuration.invalidate_paths:
            await self.controller.invalidate_cache(
                cache_configuration.invalidate_paths, storage=self.storage
            )

        if not cache_configuration.max_age:
            return None

        if not await self.controller.is_cachable_request(request):
            return None

        cache_key = await self.controller.generate_cache_key(
            request, cache_configuration=cache_configuration
        )

        cached_response = await self.controller.get_cached_response(
            cache_key, self.storage
        )
        if cached_response is not None:
            logger.debug("Returning cached response for key: %s", cache_key)
            await cached_response(scope, receive, send)
            return True

        # Cache not found - execute request and cache result
        await CacheSendWrapper(
            app=self.app,
            scope=scope,
            receive=receive,
            send=send,
            controller=self.controller,
            storage=self.storage,
            request=request,
            cache_key=cache_key,
            ttl=cache_configuration.max_age,
        )()
        return True

    def _extract_routes_info(self, routes: list[routing.APIRoute]) -> list[RouteInfo]:
        """Recursively extracts route information and their dependencies.

        Args:
            routes: List of routes to analyze
        """
        routes_info = []
        route_names = {route.name: route.path for route in routes}

        for route in routes:
            (
                cache_config,
                cache_drop_config,
            ) = self._extract_cache_configs_from_route(route)

            paths = self._convert_methods_to_path(route_names, cache_drop_config)

            if cache_drop_config and paths is not None:
                cache_drop_config.paths.extend(paths)

            if cache_config or cache_drop_config:
                cache_configuration = CacheConfiguration(
                    max_age=cache_config.max_age if cache_config else None,
                    key_func=cache_config.key_func if cache_config else None,
                    invalidate_paths=(
                        cache_drop_config.paths if cache_drop_config else None
                    ),
                )
                route_info = RouteInfo(
                    route=route,
                    cache_config=cache_configuration,
                )
                routes_info.append(route_info)

        return routes_info

    def _extract_cache_configs_from_route(
        self, route: routing.APIRoute
    ) -> tp.Tuple[CacheConfig | None, CacheDropConfig | None]:
        """Extracts cache configurations from route dependencies.

        Args:
            route: Route to analyze

        Returns:
            Tuple with CacheConfig and CacheDropConfig (if found)
        """
        cache_config = None
        cache_drop_config = None

        endpoint = getattr(route, "endpoint", None)
        if not endpoint:
            return None, None

        # Analyze dependencies if they exist
        for dependency in getattr(route, "dependencies", []):
            if isinstance(dependency, BaseCacheConfigDepends):
                # need to make a copy, as dependency can be destroyed
                dependency = copy.deepcopy(dependency)
                if isinstance(dependency, CacheConfig):
                    cache_config = dependency
                elif isinstance(dependency, CacheDropConfig):
                    cache_drop_config = dependency
                continue

        return cache_config, cache_drop_config

    def _convert_methods_to_path(
        self,
        route_names: dict[str, str],
        cache_drop_config: CacheDropConfig | None,
    ) -> list[re.Pattern] | None:
        if not cache_drop_config:
            return None

        unique: dict[str, re.Pattern] = {}

        for method in cache_drop_config.methods:
            name = get_name(method)
            route = route_names.get(name)
            if not route:
                continue

            regex = compile_path(route)[0]
            key = regex.pattern

            if key not in unique:
                unique[key] = regex

        return list(unique.values())

    def _find_matching_route(
        self, request: Request, routes_info: list[RouteInfo]
    ) -> tp.Optional[RouteInfo]:
        """Finds route matching the request.

        Args:
            request: HTTP request

        Returns:
            RouteInfo if matching route found, otherwise None
        """
        for route_info in routes_info:
            if request.method not in route_info.methods:
                continue
            match_mode, _ = route_info.route.matches(request.scope)
            if match_mode == Match.FULL:
                return route_info

        return None
