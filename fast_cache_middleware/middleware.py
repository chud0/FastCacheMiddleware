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
from .stores import AbstractCacheStore, MemoryCacheStore
import logging


logger = logging.getLogger(__name__)


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

        Если запрос – GET с конфигурацией кеширования и не пропускается (не _should_skip_cache), то:
          – если _get_cached_response вернул кешированный ответ (кеш-хит), то возвращаем его (с заголовком X-Cache: HIT);
          – если _get_cached_response вернул None (кеш-мисс), то выполняем call_next, затем (если ответ не с ошибкой) кешируем ответ (через _cache_response) и устанавливаем заголовок X-Cache: MISS/EXPIRED.

        Args:
            request: HTTP запрос
            call_next: Следующий обработчик

        Returns:
            HTTP ответ (с заголовком X-Cache: HIT/MISS/BYPASS/EXPIRED, если запрос кешируется)
        """
        logger.info(f"Request method: {request.method}, URL: {request.url}")
        
        # Получаем конфигурацию кеширования из зависимостей
        cache_config = self._get_cache_config(request)
        cache_drop_config = self._get_cache_drop_config(request)
        
        logger.info(f"cache_config: {cache_config}")
        logger.info(f"cache_drop_config: {cache_drop_config}")

        # Если это модифицирующий запрос, обрабатываем инвалидацию
        if cache_drop_config and request.method in cache_drop_config.on_methods:
            await self._handle_cache_drop(request, cache_drop_config)

        # Если это GET запрос с конфигурацией кеширования
        if request.method == "GET" and cache_config:
            logger.info("Processing GET request with cache config")
            
            # Проверяем, нужно ли пропустить кеширование
            if self._should_skip_cache(request):
                logger.info("Skipping cache (BYPASS)")
                response = await call_next(request)
                response.headers["X-Cache"] = "BYPASS"
                return response
            
            # Проверяем кеш
            cached_response = await self._get_cached_response(request, cache_config)
            if cached_response:
                logger.info("Cache HIT")
                # Кеш-хит: возвращаем кешированный ответ (с заголовком X-Cache: HIT)
                return cached_response
            else:
                logger.info("Cache MISS")

        # Кеш-мисс (или запрос не кешируется): выполняем запрос
        response = await call_next(request)

        # Если это GET запрос с конфигурацией кеширования и не пропускается, кешируем ответ
        if (
            request.method == "GET"
            and cache_config
            and not self._should_skip_cache(request)
        ):
            # Проверяем, был ли кеш устаревшим
            cache_status = getattr(request.state, "cache_status", "MISS")
            
            logger.info(f"Setting X-Cache header to: {cache_status}")
            
            # Устанавливаем заголовок X-Cache (если ответ не с ошибкой)
            if response.status_code < 400:
                response.headers["X-Cache"] = cache_status
            await self._cache_response(request, response, cache_config)

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
        logger.info(f"Route: {route}")
        if not route:
            return None

        logger.info(f"Route dependencies: {route.dependencies}")
        for dependency in route.dependencies:
            logger.info(f"Checking dependency: {dependency}")
            logger.info(f"Dependency.dependency: {dependency.dependency}")
            
            # Проверяем, есть ли в state уже вычисленные зависимости
            if hasattr(request.state, "dependency_cache"):
                dep_result = request.state.dependency_cache.get(dependency.dependency)
                if dep_result and isinstance(dep_result, CacheConfig):
                    logger.info(f"Found cached CacheConfig: {dep_result}")
                    return dep_result
            
            # Если dependency.dependency это функция, которая возвращает CacheConfig, вызываем её
            try:
                result = dependency.dependency()
                logger.info(f"Function call result: {result}, type: {type(result)}")
                if isinstance(result, CacheConfig):
                    logger.info(f"Found CacheConfig from function: {result}")
                    return result
            except Exception as e:
                logger.info(f"Failed to call dependency as function: {e}")
                # Если не получилось вызвать как функцию, проверяем прямо
                if isinstance(dependency.dependency, CacheConfig):
                    logger.info(f"Found direct CacheConfig: {dependency.dependency}")
                    return dependency.dependency

        logger.info("No CacheConfig found")
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
            # Проверяем, есть ли в state уже вычисленные зависимости
            if hasattr(request.state, "dependency_cache"):
                dep_result = request.state.dependency_cache.get(dependency.dependency)
                if dep_result and isinstance(dep_result, CacheDropConfig):
                    return dep_result
            
            # Если dependency.dependency это функция, которая возвращает CacheDropConfig, вызываем её
            try:
                result = dependency.dependency()
                if isinstance(result, CacheDropConfig):
                    return result
            except:
                # Если не получилось вызвать как функцию, проверяем прямо
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

        Если кеш-хит (cached не None), то в возвращаемый Response добавляется заголовок X-Cache со значением "HIT".
        Если кеш устарел, устанавливается флаг для статуса EXPIRED.

        Args:
            request: HTTP запрос
            config: Конфигурация кеширования

        Returns:
            Кешированный ответ (с заголовком X-Cache: HIT) или None (кеш-мисс/expired)
        """
        store = self._get_store(request)
        key = config.key_func(request)

        cached = await store.get(key)
        if not cached:
            return None

        # Проверяем, не устарел ли кеш
        import time
        if "cached_at" in cached:
            cached_at = cached["cached_at"]
            if time.time() - cached_at > config.max_age:
                # Кеш устарел, помечаем для статуса EXPIRED
                request.state.cache_status = "EXPIRED"
                return None

        # Если кеш-хит, то устанавливаем заголовок X-Cache: HIT
        resp = Response(
            content=cached["response"],
            status_code=cached["status_code"],
            headers=cached["headers"],
        )
        resp.headers["X-Cache"] = "HIT"
        return resp

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

        # Сохраняем в кеш с временной меткой
        import time
        await store.set(
            key=key,
            value={
                "response": body,
                "headers": dict(response.headers),
                "status_code": response.status_code,
                "cached_at": time.time(),
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