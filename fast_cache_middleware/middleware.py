import copy
import logging
import typing as tp

from fastapi import FastAPI, routing
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Match
from starlette.types import ASGIApp, Receive, Scope, Send

from ._helpers import set_cache_age_in_openapi_schema
from .controller import Controller
from .depends import BaseCacheConfigDepends, CacheConfig, CacheDropConfig
from .schemas import RouteInfo
from .storages import BaseStorage, InMemoryStorage

logger = logging.getLogger(__name__)


class BaseMiddleware:
    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        self.app = app

        self.executors_map = {
            "lifespan": self.on_lifespan,
            "http": self.on_http,
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope["type"]
        try:
            is_request_processed = await self.executors_map[scope_type](
                scope, receive, send
            )
        except KeyError:
            logger.debug("Not supported scope type: %s", scope_type)
            is_request_processed = False

        if not is_request_processed:
            await self.app(scope, receive, send)

    async def on_lifespan(
        self, scope: Scope, receive: Receive, send: Send
    ) -> bool | None:
        pass

    async def on_http(self, scope: Scope, receive: Receive, send: Send) -> bool | None:
        pass


class BaseSendWrapper:
    def __init__(self, app: ASGIApp, scope: Scope, receive: Receive, send: Send):
        self.app = app
        self.scope = scope
        self.receive = receive
        self.send = send

        self._response_status: int = 200
        self._response_headers: dict[str, str] = dict()
        self._response_body: bytes = b""

        self.executors_map = {
            "http.response.start": self.on_response_start,
            "http.response.body": self.on_response_body,
        }

    async def __call__(self) -> None:
        return await self.app(self.scope, self.receive, self._message_processor)

    async def _message_processor(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        try:
            executor = self.executors_map[message["type"]]
        except KeyError:
            logger.error("Not found executor for %s message type", message["type"])
        else:
            await executor(message)

        await self.send(message)

    async def on_response_start(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        self._response_status = message["status"]
        self._response_headers = {
            k.decode(): v.decode() for k, v in message.get("headers", [])
        }

    async def on_response_body(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        self._response_body += message.get("body", b"")

        # this is the last chunk
        if not message.get("more_body", False):
            response = Response(
                content=self._response_body,
                status_code=self._response_status,
                headers=self._response_headers,
            )
            await self.on_response_ready(response)

    async def on_response_ready(self, response: Response) -> None:
        pass


class CacheSendWrapper(BaseSendWrapper):
    def __init__(
        self,
        controller: Controller,
        storage: BaseStorage,
        request: Request,
        cache_key: str,
        ttl: int,
        app: ASGIApp,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        super().__init__(app, scope, receive, send)

        self.controller = controller
        self.storage = storage
        self.request = request
        self.cache_key = cache_key
        self.ttl = ttl

    async def on_response_start(self, message: tp.MutableMapping[str, tp.Any]) -> None:
        message.get("headers", []).append(("X-Cache-Status".encode(), "MISS".encode()))
        return await super().on_response_start(message)

    async def on_response_ready(self, response: Response) -> None:
        await self.controller.cache_response(
            cache_key=self.cache_key,
            request=self.request,
            response=response,
            storage=self.storage,
            ttl=self.ttl,
        )


def get_app_routes(app: FastAPI) -> tp.List[routing.APIRoute]:
    """Gets all routes from FastAPI application.

    Recursively traverses all application routers and collects their routes.

    Args:
        app: FastAPI application

    Returns:
        List of all application routes
    """
    routes = []

    # Get routes from main application router
    routes.extend(get_routes(app.router))

    # Traverse all nested routers
    for route in app.router.routes:
        if isinstance(route, Mount):
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


def get_routes(router: routing.APIRouter) -> list[routing.APIRoute]:
    """Recursively gets all routes from router.

    Traverses all routes in router and its sub-routers, collecting them into a single list.

    Args:
        router: APIRouter to traverse

    Returns:
        List of all routes from router and its sub-routers
    """
    routes = []

    # Get all routes from current router
    for route in router.routes:
        if isinstance(route, routing.APIRoute):
            routes.append(route)
        elif isinstance(route, Mount):
            # Recursively traverse sub-routers
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


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
            fastapi_app = scope["app"]
            if isinstance(fastapi_app, FastAPI):
                set_cache_age_in_openapi_schema(fastapi_app)
                self._openapi_initialized = True

        # Find matching route
        route_info = self._find_matching_route(request, self._routes_info)
        if not route_info:
            return None

        # Handle invalidation if specified
        if cc := route_info.cache_drop_config:
            await self.controller.invalidate_cache(cc, storage=self.storage)

        # Handle caching if config exists
        cache_config = route_info.cache_config
        if not cache_config:
            return None

        if not await self.controller.is_cachable_request(request):
            return None

        cache_key = await self.controller.generate_cache_key(request, cache_config)

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
            ttl=cache_config.max_age,
        )()
        return True

    def _extract_routes_info(self, routes: list[routing.APIRoute]) -> list[RouteInfo]:
        """Recursively extracts route information and their dependencies.

        Args:
            routes: List of routes to analyze
        """
        routes_info = []
        for route in routes:
            (
                cache_config,
                cache_drop_config,
            ) = self._extract_cache_configs_from_route(route)

            if cache_config or cache_drop_config:
                route_info = RouteInfo(
                    route=route,
                    cache_config=cache_config,
                    cache_drop_config=cache_drop_config,
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
