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
    url = scope["path"]
    if scope["query_string"]:
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
    4. Проверка HTTP заголовков кеширования
    5. Инвалидация кеша по паттернам URL

    Поддерживает:
    - Кастомные функции генерации ключей через CacheConfig
    - Инвалидацию кеша по URL паттернам через CacheDropConfig
    - Стандартные HTTP заголовки кеширования (Cache-Control, ETag, Last-Modified)
    - Настройка времени жизни кеша через max_age в CacheConfig
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
        """Определяет, нужно ли кешировать данный запрос.

        Args:
            request: HTTP запрос
            cache_config: Конфигурация кеширования

        Returns:
            bool: True если запрос нужно кешировать
        """
        # Кешируем только GET запросы по умолчанию
        if request.method not in self.cacheable_methods:
            return False

        # Проверяем заголовки Cache-Control
        # todo: add parsing cache-control function
        cache_control = request.headers.get("cache-control", "").lower()
        if "no-cache" in cache_control or "no-store" in cache_control:
            return False

        return True

    async def is_cachable_response(self, response: Response) -> bool:
        """Определяет, можно ли кешировать данный ответ.

        Args:
            request: HTTP запрос
            response: HTTP ответ

        Returns:
            bool: True если ответ можно кешировать
        """
        if response.status_code not in self.cacheable_status_codes:
            return False

        # Проверяем заголовки Cache-Control
        cache_control = response.headers.get("cache-control", "").lower()
        if (
            "no-cache" in cache_control
            or "no-store" in cache_control
            or "private" in cache_control
        ):
            return False

        # Проверяем размер ответа (не кешируем слишком большие ответы)
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
        """Генерирует ключ кеша для запроса.

        Args:
            request: HTTP запрос
            cache_config: Конфигурация кеширования

        Returns:
            str: Ключ кеша
        """
        # Используем пользовательскую функцию генерации ключа если есть
        if cache_config.key_func:
            return cache_config.key_func(request)

        # Используем стандартную функцию
        return generate_key(request)

    async def cache_response(
        self,
        cache_key: str,
        request: Request,
        response: Response,
        storage: BaseStorage,
        ttl: tp.Optional[int] = None,
    ) -> None:
        """Сохраняет ответ в кеш.

        Args:
            cache_key: Ключ кеша
            request: HTTP запрос
            response: HTTP ответ для кеширования
            storage: Хранилище кеша
            ttl: Время жизни кеша в секундах
        todo: в meta можно писать etag и last_modified из хедеров ответа
        """
        if await self.is_cachable_response(response):
            await storage.store(cache_key, response, request, {"ttl": ttl})
        else:
            logger.debug("Skip caching for response: %s", response.status_code)

    async def get_cached_response(
        self, cache_key: str, storage: BaseStorage
    ) -> tp.Optional[Response]:
        """Получает кешированный ответ если он существует и актуален.

        Args:
            cache_key: Ключ кеша
            storage: Хранилище кеша

        Returns:
            Response или None если кеш неактуален/отсутствует
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
        """Инвалидирует кеш по конфигурации.

        Args:
            cache_drop_config: Конфигурация инвалидации кеша
            storage: Хранилище кеша

        TODO: Комментарии по доработкам:

        1. Необходимо добавить поддержку паттернов в storage для массовой инвалидации
           по префиксу/маске ключа (особенно для Redis/Memcached)

        2. Желательно добавить bulk операции для удаления множества ключей
           за один запрос к хранилищу

        3. Можно добавить отложенную/асинхронную инвалидацию через очередь
           для больших наборов данных

        4. Стоит добавить стратегии инвалидации:
           - Немедленная (текущая реализация)
           - Отложенная (через TTL)
           - Частичная (только определенные поля)

        5. Добавить поддержку тегов для группировки связанных кешей
           и их совместной инвалидации
        """
        for path in cache_drop_config.paths:
            await storage.remove(path)
            logger.info("Инвалидирован кеш для паттерна: %s", path.pattern)
