"""
Middleware для интеллектуального кеширования FastAPI.

Этот модуль реализует middleware для кеширования ответов API
с поддержкой конфигурации через dependencies и автоматической инвалидации.
"""
import json
import logging
import time
from typing import Callable, Dict, Optional, Any

from fastapi import Request, Response
from fastapi.routing import APIRoute
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .config import CacheConfig, CacheDropConfig
from .stores import AbstractCacheStore, MemoryCacheStore

logger = logging.getLogger(__name__)


class FastCacheMiddleware(BaseHTTPMiddleware):
    """
    Middleware для интеллектуального кеширования ответов FastAPI.
    
    Поддерживает:
    - Конфигурацию через dependencies
    - Автоматическую инвалидацию кеша
    - Гибкую настройку ключей и правил
    - Заголовки X-Cache (HIT/MISS/BYPASS/EXPIRED)
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

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Основная логика обработки запроса.

        Args:
            request: HTTP запрос
            call_next: Следующий обработчик в цепочке

        Returns:
            HTTP ответ с заголовками кеширования
        """
        logger.info(f"Processing {request.method} {request.url}")

        # Выполняем запрос сначала, чтобы получить доступ к конфигурациям
        response = await call_next(request)

        # Проверяем, есть ли конфигурации кеширования в request.state
        cache_config = getattr(request.state, "cache_config", None)
        cache_drop_config = getattr(request.state, "cache_drop_config", None)

        logger.info(f"Cache config found: {cache_config is not None}")
        logger.info(f"Cache drop config found: {cache_drop_config is not None}")

        # Если это GET запрос с конфигурацией кеширования
        if request.method == "GET" and cache_config:
            return await self._handle_get_with_cache(request, response, cache_config)

        # Если это модифицирующий запрос с конфигурацией инвалидации
        if cache_drop_config and request.method in cache_drop_config.on_methods:
            await self._handle_cache_invalidation(request, cache_drop_config)

        return response

    async def _handle_get_with_cache(
        self, 
        request: Request, 
        response: Response, 
        config: CacheConfig
    ) -> Response:
        """
        Обработка GET запроса с кешированием.
        
        Поскольку запрос уже выполнен, мы можем только сохранить ответ в кеш
        и установить заголовок X-Cache: MISS.

        Args:
            request: HTTP запрос
            response: HTTP ответ
            config: Конфигурация кеширования

        Returns:
            HTTP ответ с заголовком X-Cache
        """
        # Проверяем, нужно ли пропустить кеш
        if self._should_bypass_cache(request):
            response.headers["X-Cache"] = "BYPASS"
            logger.info("Cache bypassed")
            return response

        # Генерируем ключ кеша
        cache_key = config.key_func(request)
        store = self._get_store(config)

        # Проверяем кеш (для будущих запросов)
        cached_data = await store.get(cache_key)
        
        if cached_data:
            # Проверяем, не истек ли кеш
            if self._is_cache_expired(cached_data, config.max_age):
                logger.info(f"Cache expired for key: {cache_key}")
                response.headers["X-Cache"] = "EXPIRED"
                await self._store_response(store, cache_key, response, config)
                return response
            
            # Кеш-хит (но мы уже выполнили запрос, так что это для следующего раза)
            logger.info(f"Cache exists for key: {cache_key}")
            response.headers["X-Cache"] = "MISS"  # Текущий запрос все равно MISS
        else:
            # Кеш-мисс
            logger.info(f"Cache miss for key: {cache_key}")
            response.headers["X-Cache"] = "MISS"
        
        # Сохраняем в кеш если ответ успешный
        if response.status_code < 400:
            await self._store_response(store, cache_key, response, config)

        return response

    async def _handle_cache_invalidation(
        self, 
        request: Request, 
        config: CacheDropConfig
    ) -> None:
        """
        Обработка инвалидации кеша.

        Args:
            request: HTTP запрос
            config: Конфигурация инвалидации
        """
        store = self.default_store

        # Инвалидация по шаблону ключа
        if config.key_template:
            key = config.key_template.format(**request.path_params)
            await store.delete_pattern(key)
            logger.info(f"Invalidated cache by key template: {key}")

        # Инвалидация по путям
        for path in config.paths:
            path_key = path.format(**request.path_params)
            await store.delete_pattern(path_key)
            logger.info(f"Invalidated cache for path: {path_key}")

    def _should_bypass_cache(self, request: Request) -> bool:
        """
        Проверка, нужно ли обходить кеш.

        Args:
            request: HTTP запрос

        Returns:
            True, если кеш нужно обойти
        """
        cache_control = request.headers.get("cache-control", "").lower()
        return "no-cache" in cache_control or "no-store" in cache_control

    def _is_cache_expired(self, cached_data: Dict, max_age: int) -> bool:
        """
        Проверка истечения кеша.

        Args:
            cached_data: Данные из кеша
            max_age: Максимальный возраст в секундах

        Returns:
            True, если кеш истек
        """
        cached_at = cached_data.get("cached_at", 0)
        return time.time() - cached_at > max_age

    def _create_response_from_cache(self, cached_data: Dict) -> Response:
        """
        Создание ответа из кешированных данных.

        Args:
            cached_data: Данные из кеша

        Returns:
            HTTP ответ
        """
        return Response(
            content=cached_data["content"],
            status_code=cached_data["status_code"],
            headers=cached_data["headers"],
            media_type=cached_data.get("media_type")
        )

    async def _store_response(
        self, 
        store: AbstractCacheStore, 
        cache_key: str, 
        response: Response, 
        config: CacheConfig
    ) -> None:
        """
        Сохранение ответа в кеш.

        Args:
            store: Хранилище кеша
            cache_key: Ключ кеша
            response: HTTP ответ
            config: Конфигурация кеширования
        """
        # Получаем тело ответа
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        # Правильно восстанавливаем тело ответа
        response.body = body
        
        # Создаем новый body_iterator из сохраненного тела
        async def body_iterator():
            yield body
        
        response.body_iterator = body_iterator()

        # Подготавливаем данные для кеширования
        cache_data = {
            "content": body,
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "media_type": response.media_type,
            "cached_at": time.time(),
        }

        # Сохраняем в кеш
        await store.set(cache_key, cache_data, config.max_age)
        logger.info(f"Stored response in cache with key: {cache_key}")

    def _get_store(self, config: CacheConfig) -> AbstractCacheStore:
        """
        Получение хранилища кеша.

        Args:
            config: Конфигурация кеширования

        Returns:
            Экземпляр хранилища кеша
        """
        # Пока используем default_store
        # В будущем можно добавить логику выбора на основе config.cache_store
        return self.default_store


# Функции-помощники для использования в dependencies
def cache_dependency(config: CacheConfig):
    """
    Dependency для установки конфигурации кеширования.
    
    Args:
        config: Конфигурация кеширования
    """
    def dependency(request: Request):
        request.state.cache_config = config
        return config
    
    return dependency


def cache_drop_dependency(config: CacheDropConfig):
    """
    Dependency для установки конфигурации инвалидации.
    
    Args:
        config: Конфигурация инвалидации
    """
    def dependency(request: Request):
        request.state.cache_drop_config = config
        return config
    
    return dependency 