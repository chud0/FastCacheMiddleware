import copy
import inspect
import logging
import typing as tp

from fastapi import FastAPI, routing
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .controller import Controller
from .depends import BaseCacheConfigDepends, CacheConfig, CacheDropConfig
from .schemas import RouteInfo
from .storages import BaseStorage, InMemoryStorage

logger = logging.getLogger(__name__)


def get_app_routes(app: FastAPI) -> tp.List[routing.APIRoute]:
    """Получает все роуты из FastAPI приложения.

    Рекурсивно обходит все роутеры приложения и собирает их роуты.

    Args:
        app: FastAPI приложение

    Returns:
        Список всех роутов приложения
    """
    routes = []

    # Получаем роуты из основного роутера приложения
    routes.extend(get_routes(app.router))

    # Обходим все вложенные роутеры
    for route in app.router.routes:
        if isinstance(route, Mount):
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


def get_routes(router: routing.APIRouter) -> list[routing.APIRoute]:
    """Рекурсивно получает все роуты из роутера.

    Обходит все роуты в роутере и его подроутерах, собирая их в единый список.

    Args:
        router: APIRouter для обхода

    Returns:
        Список всех роутов из роутера и его подроутеров
    """
    routes = []

    # Получаем все роуты из текущего роутера
    for route in router.routes:
        if isinstance(route, routing.APIRoute):
            routes.append(route)
        elif isinstance(route, Mount):
            # Рекурсивно обходим подроутеры
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


async def build_response_with_callback(
    app: ASGIApp,
    scope: Scope,
    receive: Receive,
    send: Send,
    on_response_ready: tp.Callable[[Response], tp.Awaitable[None]],
) -> None:
    response_holder: tp.Dict[str, tp.Any] = {}

    async def response_builder(message: tp.Dict[str, tp.Any]) -> None:
        """Wrapper для перехвата и сохранения ответа."""
        if message["type"] == "http.response.start":
            response_holder["status"] = message["status"]
            response_holder["headers"] = [
                (k.decode(), v.decode()) for k, v in message.get("headers", [])
            ]
            response_holder["body"] = b""
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            response_holder["body"] += body

            # Если это последний chunk, кешируем ответ
            if not message.get("more_body", False):
                response = Response(
                    content=response_holder["body"],
                    status_code=response_holder["status"],
                    headers=dict(response_holder["headers"]),
                )

                # Вызываем коллбэк с готовым ответом
                await on_response_ready(response)

        # Передаем событие дальше
        await send(message)

    await app(scope, receive, response_builder)


class FastCacheMiddleware:
    """Middleware для кеширования ответов в ASGI приложениях.

    Подход с резолюцией роутов:
    1. На старте анализирует все роуты и их dependencies
    2. При запросе находит соответствующий роут по path и методу
    3. Извлекает кеш конфигурацию из dependencies этого роута
    4. Выполняет стандартную логику кеширования/инвалидации

    Преимущества:
    - Предварительный анализ роутов - быстрый поиск конфигурации
    - Поддержка всех FastAPI dependencies
    - Гибкое управление кешированием на уровне роутов
    - Эффективная инвалидация кеша

    Args:
        app: ASGI приложение для оборачивания
        storage: Хранилище для кеша (по умолчанию InMemoryStorage)
        controller: Контроллер для управления логикой кеширования
    """

    def __init__(
        self,
        app: ASGIApp,
        storage: tp.Optional[BaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self.app = app
        self.storage = storage or InMemoryStorage()
        self.controller = controller or Controller()

    def _extract_routes_info(self, routes: list[routing.APIRoute]) -> list[RouteInfo]:
        """Рекурсивно извлекает информацию о роутах и их dependencies.

        Args:
            routes: Список роутов для анализа
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
        """Извлекает кеш конфигурации из dependencies роута.

        Args:
            route: Роут для анализа

        Returns:
            Tuple с CacheConfig и CacheDropConfig (если найдены)
        """
        cache_config = None
        cache_drop_config = None

        endpoint = getattr(route, "endpoint", None)
        if not endpoint:
            return None, None

        # Анализируем dependencies если они есть
        for dependency in getattr(route, "dependencies", []):
            if isinstance(dependency, BaseCacheConfigDepends):
                # нужно сделать копию, т.к. dependency может быть уничтожен
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
        """Находит роут, соответствующий запросу.

        Args:
            request: HTTP запрос

        Returns:
            RouteInfo если найден соответствующий роут, иначе None
        """
        for route_info in routes_info:
            match_mode, _ = route_info.route.matches(request.scope)
            if match_mode == routing.Match.FULL:
                return route_info

        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app_routes = get_app_routes(scope["app"])
        routes_info = self._extract_routes_info(app_routes)

        request = Request(scope, receive)

        # Находим соответствующий роут
        route_info = self._find_matching_route(request, routes_info)
        if not route_info:
            await self.app(scope, receive, send)
            return

        # Обрабатываем инвалидацию если указано
        if route_info.cache_drop_config:
            await self._handle_cache_invalidation(route_info, request)

        # Обрабатываем кеширование если конфиг есть
        if route_info.cache_config:
            await self._handle_cache_request(route_info, request, scope, receive, send)
            return

        # Выполняем оригинальный запрос
        await self.app(scope, receive, send)

    async def _handle_cache_request(
        self,
        route_info: RouteInfo,
        request: Request,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Обрабатывает запрос с кешированием.

        Args:
            route_info: Информация о роуте
            request: HTTP запрос
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        cache_config = route_info.cache_config
        if not cache_config:
            await self.app(scope, receive, send)
            return

        if not await self.controller.is_cachable_request(request):
            await self.app(scope, receive, send)
            return

        cache_key = await self.controller.generate_cache_key(request, cache_config)

        cached_response = await self.controller.get_cached_response(
            cache_key, self.storage
        )
        if cached_response is not None:
            logger.debug("Возвращаем кешированный ответ для ключа: %s", cache_key)
            await cached_response(scope, receive, send)
            return

        # Кеш не найден - выполняем запрос и кешируем результат
        await build_response_with_callback(
            self.app,
            scope,
            receive,
            send,
            lambda response: self.controller.cache_response(
                cache_key, request, response, self.storage, cache_config.max_age
            ),
        )

    async def _handle_cache_invalidation(
        self, route_info: RouteInfo, request: Request
    ) -> None:
        """Обрабатывает инвалидацию кеша.

        Args:
            route_info: Информация о роуте
            request: HTTP запрос
        """
        if cc := route_info.cache_drop_config:
            await self.controller.invalidate_cache(cc, storage=self.storage)
