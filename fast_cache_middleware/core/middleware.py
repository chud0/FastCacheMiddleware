"""
Основной middleware для кеширования.

Этот модуль реализует основной middleware для кеширования
ответов FastAPI.
"""
import json
from typing import Callable, Optional, Type

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .config import CacheConfig, CacheDropConfig
from .types import BaseCacheStore, CacheValue
from ..stores.base import AbstractCacheStore


class FastCacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware для кеширования ответов FastAPI.

    Этот middleware обрабатывает кеширование и инвалидацию
    кеша для HTTP запросов.
    """

    def __init__(
        self,
        app: ASGIApp,
        default_store: Optional[AbstractCacheStore] = None,
    ) -> None:
        """
        Инициализация middleware.

        Args:
            app: ASGI приложение
            default_store: Хранилище кеша по умолчанию
        """
        super().__init__(app)
        self.default_store = default_store or MemoryCacheStore()

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ) -> Response:
        """
        Обработка запроса.

        Args:
            request: HTTP запрос
            call_next: Следующий обработчик

        Returns:
            HTTP ответ
        """
        # Получаем конфигурацию кеширования из зависимостей
        cache_config = self._get_cache_config(request)
        cache_drop_config = self._get_cache_drop_config(request)

        # Если это модифицирующий запрос, обрабатываем инвалидацию
        if cache_drop_config and request.method in cache_drop_config.on_methods:
            await self._handle_cache_drop(request, cache_drop_config)

        # Если это GET запрос с конфигурацией кеширования,
        # проверяем кеш
        if (
            request.method == "GET"
            and cache_config
            and not self._should_skip_cache(request)
        ):
            cached_response = await self._get_cached_response(
                request,
                cache_config,
            )
            if cached_response:
                return cached_response

        # Выполняем запрос
        response = await call_next(request)

        # Если это GET запрос с конфигурацией кеширования,
        # сохраняем ответ в кеш
        if (
            request.method == "GET"
            and cache_config
            and not self._should_skip_cache(request)
        ):
            await self._cache_response(
                request,
                response,
                cache_config,
            )

        return response

    def _get_cache_config(
        self,
        request: Request,
    ) -> Optional[CacheConfig]:
        """
        Получить конфигурацию кеширования из зависимостей.

        Args:
            request: HTTP запрос

        Returns:
            Конфигурация кеширования или None
        """
        route: Optional[APIRoute] = request.scope.get("route")
        if not route:
            return None

        for dependency in route.dependencies:
            if isinstance(dependency.dependency, CacheConfig):
                return dependency.dependency

        return None

    def _get_cache_drop_config(
        self,
        request: Request,
    ) -> Optional[CacheDropConfig]:
        """
        Получить конфигурацию инвалидации из зависимостей.

        Args:
            request: HTTP запрос

        Returns:
            Конфигурация инвалидации или None
        """
        route: Optional[APIRoute] = request.scope.get("route")
        if not route:
            return None

        for dependency in route.dependencies:
            if isinstance(dependency.dependency, CacheDropConfig):
                return dependency.dependency

        return None

    async def _handle_cache_drop(
        self,
        request: Request,
        config: CacheDropConfig,
    ) -> None:
        """
        Обработать инвалидацию кеша.

        Args:
            request: HTTP запрос
            config: Конфигурация инвалидации
        """
        store = self._get_store(request)

        # Инвалидируем по шаблону ключа
        if config.key_template:
            key = config.key_template.format(**request.path_params)
            await store.delete_pattern(key)

        # Инвалидируем по путям
        for path in config.paths:
            # Заменяем параметры пути на значения из запроса
            path_key = path.format(**request.path_params)
            await store.delete_pattern(path_key)

    async def _get_cached_response(
        self,
        request: Request,
        config: CacheConfig,
    ) -> Optional[Response]:
        """
        Получить кешированный ответ.

        Args:
            request: HTTP запрос
            config: Конфигурация кеширования

        Returns:
            Кешированный ответ или None
        """
        store = self._get_store(request)
        key = config.key_func(request)

        cached = await store.get(key)
        if not cached:
            return None

        return Response(
            content=cached["response"],
            status_code=cached["status_code"],
            headers=cached["headers"],
        )

    async def _cache_response(
        self,
        request: Request,
        response: Response,
        config: CacheConfig,
    ) -> None:
        """
        Сохранить ответ в кеш.

        Args:
            request: HTTP запрос
            response: HTTP ответ
            config: Конфигурация кеширования
        """
        # Не кешируем ответы с ошибками
        if response.status_code >= 400:
            return

        store = self._get_store(request)
        key = config.key_func(request)

        # Получаем тело ответа
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Создаем копию ответа с телом
        response.body = body

        # Сохраняем в кеш
        await store.set(
            key=key,
            value={
                "response": body,
                "headers": dict(response.headers),
                "status_code": response.status_code,
            },
            max_age=config.max_age,
        )

    def _get_store(self, request: Request) -> AbstractCacheStore:
        """
        Получить хранилище кеша для запроса.

        Args:
            request: HTTP запрос

        Returns:
            Хранилище кеша
        """
        # В будущем здесь можно добавить логику выбора
        # хранилища на основе конфигурации
        return self.default_store

    def _should_skip_cache(self, request: Request) -> bool:
        """
        Проверить, нужно ли пропустить кеширование.

        Args:
            request: HTTP запрос

        Returns:
            True, если кеширование нужно пропустить
        """
        # Пропускаем кеширование для запросов с заголовком
        # Cache-Control: no-cache
        if "no-cache" in request.headers.get("cache-control", "").lower():
            return True

        # Пропускаем кеширование для запросов с заголовком
        # Cache-Control: no-store
        if "no-store" in request.headers.get("cache-control", "").lower():
            return True

        return False 