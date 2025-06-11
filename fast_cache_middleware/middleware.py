import logging
import typing as tp
from starlette.types import ASGIApp, Scope
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, Mount
from .storages import BaseStorage, InMemoryStorage
from .controller import Controller
from uvicorn._types import ASGIReceiveCallable, ASGISendCallable
from .depends import BaseCacheConfigDepends, CacheConfig, CacheDropConfig
import inspect
from fastapi import FastAPI, routing
import copy


logger = logging.getLogger(__name__)


def get_app_routes(app: FastAPI) -> tp.List[routing.BaseRoute]:
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


def get_routes(router: routing.APIRouter) -> tp.List[routing.BaseRoute]:
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
        if isinstance(route, Route):
            routes.append(route)
        elif isinstance(route, Mount):
            # Рекурсивно обходим подроутеры
            if isinstance(route.app, routing.APIRouter):
                routes.extend(get_routes(route.app))

    return routes


class RouteInfo:
    """Информация о роуте с кеш конфигурацией."""

    def __init__(
        self,
        route: Route,
        cache_config: tp.Optional[BaseCacheConfigDepends] = None,
        cache_drop_config: tp.Optional[BaseCacheConfigDepends] = None,
    ):
        self.route = route
        self.cache_config = cache_config
        self.cache_drop_config = cache_drop_config
        self.path_regex = getattr(route, "path_regex", None)
        self.methods = getattr(route, "methods", set())


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

    def _extract_routes_info(self, routes: tp.List) -> tp.List[RouteInfo]:
        """Рекурсивно извлекает информацию о роутах и их dependencies.

        Args:
            routes: Список роутов для анализа
        """
        routes_info = []
        for route in routes:
            # Обрабатываем обычные Route
            if isinstance(route, Route):
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
            else:
                logger.warning(f"Неизвестный тип роута: {type(route)}")

        return routes_info

    def _extract_cache_configs_from_route(
        self, route: Route
    ) -> tp.Tuple[
        tp.Optional[BaseCacheConfigDepends], tp.Optional[BaseCacheConfigDepends]
    ]:
        """Извлекает кеш конфигурации из dependencies роута.

        Args:
            route: Роут для анализа

        Returns:
            Tuple с CacheConfig и CacheDropConfig (если найдены)
        """
        cache_config = None
        cache_drop_config = None

        try:
            # Получаем функцию-обработчик роута
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

        except Exception as e:
            logger.debug(f"Ошибка анализа dependencies роута {route}: {e}")

        return cache_config, cache_drop_config

    def _find_matching_route(self, request: Request) -> tp.Optional[RouteInfo]:
        """Находит роут, соответствующий запросу.

        Args:
            request: HTTP запрос

        Returns:
            RouteInfo если найден соответствующий роут, иначе None
        """
        request_path = request.url.path
        request_method = request.method

        for route_info in self.routes_info:
            # Проверяем метод
            if route_info.methods and request_method not in route_info.methods:
                continue

            # Проверяем путь
            if route_info.path_regex:
                match = route_info.path_regex.match(request_path)
                if match:
                    return route_info
            else:
                # Fallback на простое сравнение
                route_path = getattr(route_info.route, "path", "")
                if route_path == request_path:
                    return route_info

        return None

    async def __call__(
        self, scope: Scope, receive: ASGIReceiveCallable, send: ASGISendCallable
    ) -> None:
        """Основная логика middleware с резолюцией роутов."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app_routes = get_app_routes(scope["app"])
        self.routes_info: tp.List[RouteInfo] = self._extract_routes_info(app_routes)

        request = Request(scope, receive)

        # Проверяем, стоит ли искать кеш для этого метода
        if not self._should_check_cache_for_method(request.method):
            await self.app(scope, receive, send)
            return

        # Находим соответствующий роут
        route_info = self._find_matching_route(request)
        if not route_info:
            await self.app(scope, receive, send)
            return

        # Обрабатываем кеширование для GET запросов
        if request.method == "GET" and route_info.cache_config:
            await self._handle_cache_request(route_info, request, scope, receive, send)
            return

        # Обрабатываем инвалидацию для модифицирующих запросов
        if (
            request.method in ("POST", "PUT", "DELETE", "PATCH")
            and route_info.cache_drop_config
        ):
            await self._handle_cache_invalidation(route_info, request)

        # Выполняем оригинальный запрос
        await self.app(scope, receive, send)

    def _should_check_cache_for_method(self, method: str) -> bool:
        """Проверяет, стоит ли проверять кеш для данного HTTP метода.

        Args:
            method: HTTP метод

        Returns:
            bool: True если метод может использовать кеширование
        """
        # Кешируем только GET, инвалидируем для остальных
        return method in ("GET", "POST", "PUT", "DELETE", "PATCH")

    async def _handle_cache_request(
        self,
        route_info: RouteInfo,
        request: Request,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        """Обрабатывает запрос с кешированием.

        Args:
            route_info: Информация о роуте
            request: HTTP запрос
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        try:
            # Получаем кеш конфигурацию
            cache_config = route_info.cache_config
        except Exception as e:
            logger.warning(f"Ошибка при получении кеш конфигурации: {e}")
            await self.app(scope, receive, send)
            return

        try:
            # Проверяем, нужно ли кешировать этот запрос
            should_cache = await self.controller.should_cache_request(
                request, cache_config
            )
            if not should_cache:
                await self.app(scope, receive, send)
                return

            # Генерируем ключ кеша
            if hasattr(cache_config, "key_func") and cache_config.key_func:
                cache_key = cache_config.key_func(request)
            else:
                cache_key = await self.controller.generate_cache_key(request)

            # Проверяем кеш
            cached_response = await self.controller.get_cached_response(
                cache_key, request, self.storage
            )

            if cached_response is not None:
                logger.debug(f"Возвращаем кешированный ответ для ключа: {cache_key}")
                await cached_response(scope, receive, send)
                return
        except Exception as e:
            logger.warning(f"Ошибка при обработке кеширования: {e}")
            # При ошибке выполняем запрос без кеширования
            await self.app(scope, receive, send)

        # Кеш не найден - выполняем запрос и кешируем результат
        await self._execute_and_cache_request(
            cache_config, cache_key, request, scope, receive, send
        )

    async def _execute_and_cache_request(
        self,
        cache_config: CacheConfig,
        cache_key: str,
        request: Request,
        scope: Scope,
        receive: ASGIReceiveCallable,
        send: ASGISendCallable,
    ) -> None:
        """Выполняет запрос и кеширует результат.

        Args:
            cache_config: Конфигурация кеширования
            cache_key: Ключ кеша
            request: HTTP запрос
            scope: ASGI scope
            receive: ASGI receive callable
            send: ASGI send callable
        """
        response_holder: tp.Dict[str, tp.Any] = {}

        async def send_wrapper(message: tp.Dict[str, tp.Any]) -> None:
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

                    # Проверяем, можно ли кешировать ответ
                    should_cache_response = await self.controller.should_cache_response(
                        request, response
                    )

                    if should_cache_response:
                        # Создаем метаданные с TTL из конфигурации
                        metadata = {
                            "cached_at": self.controller._get_current_time_iso(),
                            "ttl": getattr(
                                cache_config, "max_age", self.controller.default_ttl
                            ),
                        }

                        await self.storage.store(cache_key, response, request, metadata)
                        logger.debug(f"Сохранили ответ в кеш с ключом: {cache_key}")

            await send(message)

        # Выполняем оригинальный запрос
        await self.app(scope, receive, send_wrapper)

    async def _handle_cache_invalidation(
        self, route_info: RouteInfo, request: Request
    ) -> None:
        """Обрабатывает инвалидацию кеша.

        Args:
            route_info: Информация о роуте
            request: HTTP запрос
        """
        try:
            cache_drop_config = route_info.cache_drop_config()

            if hasattr(cache_drop_config, "paths"):
                logger.info(f"Инвалидация кеша для путей: {cache_drop_config.paths}")
                # В реальной реализации здесь будет логика инвалидации по паттернам

        except Exception as e:
            logger.warning(f"Ошибка при инвалидации кеша: {e}")
