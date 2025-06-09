import typing as tp
from starlette.responses import Response
from starlette.requests import Request
import http
from hashlib import blake2b
from datetime import datetime, timedelta
import re
from email.utils import parsedate_to_datetime

if tp.TYPE_CHECKING:
    from .storages import BaseStorage
    from .depends import BaseCacheConfigDepends, CacheConfig, CacheDropConfig


def generate_key(request: Request) -> str:
    """Генерирует быстрый уникальный ключ для кеширования HTTP запроса.

    Args:
        request: Объект запроса Starlette Request.

    Returns:
        str: Уникальный ключ для кеширования, основанный на методе и пути запроса.
        Использует быстрый алгоритм хеширования blake2b.
        
    Note:
        Не учитывает схему и хост, так как обычно запросы идут на один и тот же хост.
        Учитывает только метод, путь и query параметры для максимальной производительности.
    """

    
    # Получаем только необходимые компоненты из scope
    scope = request.scope
    url = scope['path']
    if scope['query_string']:
        url += f"?{scope['query_string'].decode('ascii')}"

    # Используем быстрый алгоритм blake2b с минимальным размером дайджеста
    key = blake2b(digest_size=8)
    key.update(request.method.encode())
    key.update(url.encode())
    
    return key.hexdigest()


class Controller:
    """Контроллер кеширования для Starlette/FastAPI.
    
    Зона ответственности:
    1. Определение правил кеширования запросов и ответов
    2. Генерация ключей кеша с учетом пользовательских функций
    3. Управление TTL и валидацией кешированных данных
    4. Обработка инвалидации кеша по паттернам URL
    5. Проверка HTTP заголовков кеширования
    6. Интеграция с FastAPI dependencies через ASGI scope extensions
    
    Поддерживает:
    - Кастомные функции генерации ключей через CacheConfig
    - Инвалидацию кеша по URL паттернам через CacheDropConfig
    - Стандартные HTTP заголовки кеширования (Cache-Control, ETag, Last-Modified)
    - Настраиваемый TTL для различных маршрутов
    """
    
    def __init__(self, default_ttl: int = 300) -> None:
        """Инициализация контроллера.
        
        Args:
            default_ttl: TTL по умолчанию в секундах (5 минут)
        """
        self.default_ttl = default_ttl
    
    def _extract_cache_config(self, request: Request) -> tp.Tuple[tp.Optional["CacheConfig"], tp.Optional["CacheDropConfig"]]:
        """Извлекает конфигурацию кеширования из ASGI scope extensions.
        
        Args:
            request: HTTP запрос
            
        Returns:
            Tuple с CacheConfig и CacheDropConfig (если найдены)
        """
        try:
            # Используем стандартный ASGI extensions механизм
            extensions = request.scope.get("extensions", {})
            fast_cache_ext = extensions.get("fast_cache", {})
            cache_config = fast_cache_ext.get("config")
            
            if cache_config is None:
                return None, None
            
            # Импортируем классы конфигурации динамически
            from .depends import CacheConfig, CacheDropConfig
            
            if isinstance(cache_config, CacheConfig):
                return cache_config, None
            elif isinstance(cache_config, CacheDropConfig):
                return None, cache_config
            
            return None, None
            
        except Exception as e:
            # В случае ошибки возвращаем None
            import logging
            logging.getLogger(__name__).debug(f"Ошибка извлечения cache config: {e}")
            return None, None
    
    async def should_cache_request(self, request: Request, cache_config: tp.Optional["CacheConfig"]) -> bool:
        """Определяет, нужно ли кешировать данный запрос.
        
        Args:
            request: HTTP запрос
            
        Returns:
            bool: True если запрос нужно кешировать
        """
        # Кешируем только GET запросы по умолчанию
        if request.method != "GET":
            return False
        
        # Проверяем заголовки Cache-Control
        cache_control = request.headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False

        if cache_config is None:
            return False
            
        return True
    
    async def should_cache_response(
        self, 
        request: Request, 
        response: Response
    ) -> bool:
        """Определяет, можно ли кешировать данный ответ.
        
        Args:
            request: HTTP запрос
            response: HTTP ответ
            
        Returns:
            bool: True если ответ можно кешировать
        """
        # Не кешируем ошибки
        if response.status_code >= 400:
            return False
            
        # Проверяем заголовки ответа
        cache_control = response.headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control or "private" in cache_control:
            return False
        
        # Проверяем размер ответа (не кешируем слишком большие ответы)
        if hasattr(response, 'body') and response.body and len(response.body) > 1024 * 1024:  # 1MB
            return False
        
        return True
    
    async def generate_cache_key(self, request: Request) -> str:
        """Генерирует ключ кеша для запроса.
        
        Args:
            request: HTTP запрос
            
        Returns:
            str: Ключ кеша
        """
        cache_config, _ = self._extract_cache_config(request)
        
        # Используем пользовательскую функцию генерации ключа если есть
        if cache_config and hasattr(cache_config, 'key_func') and cache_config.key_func:
            return cache_config.key_func(request)
        
        # Используем стандартную функцию
        return generate_key(request)
    
    async def get_cached_response(
        self,
        cache_key: str,
        request: Request,
        storage: "BaseStorage"
    ) -> tp.Optional[Response]:
        """Получает кешированный ответ если он существует и актуален.
        
        Args:
            cache_key: Ключ кеша
            request: HTTP запрос
            storage: Хранилище кеша
            
        Returns:
            Response или None если кеш неактуален/отсутствует
        """
        try:
            stored_data = await storage.retrieve(cache_key)
            if stored_data is None:
                return None
                
            cached_response, cached_request, metadata = stored_data
            
            # Проверяем TTL
            if self._is_expired(metadata):
                return None
            
            # Проверяем условные заголовки
            if self._check_conditional_headers(request, cached_response, metadata):
                return cached_response
                
            return cached_response
            
        except Exception as e:
            # Логируем ошибку но продолжаем без кеша
            import logging
            logging.getLogger(__name__).warning(f"Ошибка получения кеша: {e}")
            return None
    
    async def cache_response(
        self,
        cache_key: str,
        request: Request,
        response: Response,
        storage: "BaseStorage"
    ) -> None:
        """Сохраняет ответ в кеш.
        
        Args:
            cache_key: Ключ кеша
            request: HTTP запрос
            response: HTTP ответ для кеширования
            storage: Хранилище кеша
        """
        try:
            # Получаем TTL из конфигурации
            cache_config, _ = self._extract_cache_config(request)
            ttl = self.default_ttl
            
            if cache_config and hasattr(cache_config, 'max_age'):
                ttl = cache_config.max_age
            
            # Создаем метаданные
            metadata = {
                "cached_at": datetime.utcnow().isoformat(),
                "ttl": ttl,
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
            }
            
            await storage.store(cache_key, response, request, metadata)
            
        except Exception as e:
            # Логируем ошибку но не прерываем обработку
            import logging
            logging.getLogger(__name__).warning(f"Ошибка сохранения в кеш: {e}")
    
    async def handle_cache_invalidation(
        self,
        request: Request,
        storage: "BaseStorage"
    ) -> None:
        """Обрабатывает инвалидацию кеша по конфигурации.
        
        Args:
            request: HTTP запрос
            storage: Хранилище кеша
        """
        _, cache_drop_config = self._extract_cache_config(request)
        if cache_drop_config is None:
            return
        
        # Для InMemoryStorage пока не реализуем массовую инвалидацию
        # В реальных хранилищах (Redis, Memcached) здесь будет поиск по паттерну
        import logging
        logging.getLogger(__name__).info(
            f"Запрос на инвалидацию кеша для путей: {cache_drop_config.paths}"
        )
    
    def _is_expired(self, metadata: tp.Dict[str, tp.Any]) -> bool:
        """Проверяет, истек ли срок действия кеша.
        
        Args:
            metadata: Метаданные кешированного объекта
            
        Returns:
            bool: True если кеш истек
        """
        try:
            cached_at = datetime.fromisoformat(metadata["cached_at"])
            ttl = metadata.get("ttl", self.default_ttl)
            expires_at = cached_at + timedelta(seconds=ttl)
            return datetime.utcnow() > expires_at
        except (KeyError, ValueError, TypeError):
            # Если не можем определить время - считаем истекшим
            return True
    
    def _check_conditional_headers(
        self,
        request: Request,
        cached_response: Response,
        metadata: tp.Dict[str, tp.Any]
    ) -> bool:
        """Проверяет условные заголовки HTTP кеширования.
        
        Args:
            request: Текущий запрос
            cached_response: Кешированный ответ
            metadata: Метаданные кеша
            
        Returns:
            bool: True если кешированный ответ актуален
        """
        # Проверка If-None-Match (ETag)
        if_none_match = request.headers.get("if-none-match")
        etag = metadata.get("etag")
        if if_none_match and etag:
            if if_none_match == "*" or etag in if_none_match:
                return True
        
        # Проверка If-Modified-Since
        if_modified_since = request.headers.get("if-modified-since")
        last_modified = metadata.get("last_modified")
        if if_modified_since and last_modified:
            try:
                if_modified_dt = parsedate_to_datetime(if_modified_since)
                last_modified_dt = parsedate_to_datetime(last_modified)
                if last_modified_dt <= if_modified_dt:
                    return True
            except (ValueError, TypeError):
                pass
        
        return True
    
    def _get_current_time_iso(self) -> str:
        """Возвращает текущее время в ISO формате.
        
        Returns:
            str: Текущее время в ISO формате
        """
        return datetime.utcnow().isoformat()
