"""
Типы и протоколы для FastCacheMiddleware.

Этот модуль определяет основные типы и протоколы, используемые в middleware.
"""
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Protocol, Type, Union

from fastapi import Request
from starlette.responses import Response
from typing_extensions import TypedDict


class CacheVisibility(str, Enum):
    """Видимость кеша."""

    PUBLIC = "public"
    PRIVATE = "private"


class CacheKey(TypedDict):
    """Структура ключа кеша."""

    key: str
    visibility: CacheVisibility
    max_age: int


class CacheValue(TypedDict):
    """Структура значения кеша."""

    response: bytes
    headers: Dict[str, str]
    status_code: int


class BaseCacheStore(Protocol):
    """
    Протокол для реализации хранилищ кеша.

    Определяет базовый интерфейс для всех реализаций хранилищ кеша.
    """

    async def get(self, key: str) -> Optional[CacheValue]:
        """
        Получить значение из кеша.

        Args:
            key: Ключ кеша

        Returns:
            Значение кеша или None, если значение не найдено
        """
        ...

    async def set(
        self,
        key: str,
        value: CacheValue,
        max_age: int,
    ) -> None:
        """
        Сохранить значение в кеш.

        Args:
            key: Ключ кеша
            value: Значение для сохранения
            max_age: Время жизни в секундах
        """
        ...

    async def delete(self, key: str) -> None:
        """
        Удалить значение из кеша.

        Args:
            key: Ключ кеша
        """
        ...

    async def delete_pattern(self, pattern: str) -> None:
        """
        Удалить все значения, соответствующие шаблону.

        Args:
            pattern: Шаблон ключа (например, "user_*")
        """
        ...


class CacheKeyGenerator(Protocol):
    """
    Протокол для генераторов ключей кеша.

    Определяет интерфейс для генерации ключей кеша на основе запроса.
    """

    def __call__(self, request: Request) -> str:
        """
        Сгенерировать ключ кеша на основе запроса.

        Args:
            request: HTTP запрос

        Returns:
            Строковый ключ кеша
        """
        ...


class CacheInvalidator(Protocol):
    """
    Протокол для инвалидаторов кеша.

    Определяет интерфейс для инвалидации кеша на основе запроса.
    """

    def __call__(
        self,
        request: Request,
        store: BaseCacheStore,
    ) -> None:
        """
        Инвалидировать кеш на основе запроса.

        Args:
            request: HTTP запрос
            store: Хранилище кеша
        """
        ...


# Типы для конфигурации
KeyFunc = Callable[[Request], str]
CacheStoreType = Type[BaseCacheStore]
HTTPMethod = str
PathTemplate = str
KeyTemplate = str 