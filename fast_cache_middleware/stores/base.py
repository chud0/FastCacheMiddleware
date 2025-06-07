"""
Базовый класс для хранилищ кеша.

Этот модуль определяет абстрактный базовый класс для всех реализаций хранилищ кеша.
"""
from abc import ABC, abstractmethod
from typing import Optional

from ..core.types import BaseCacheStore, CacheValue


class AbstractCacheStore(ABC, BaseCacheStore):
    """
    Абстрактный базовый класс для хранилищ кеша.

    Этот класс реализует протокол BaseCacheStore и предоставляет
    базовую функциональность для всех хранилищ кеша.
    """

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheValue]:
        """
        Получить значение из кеша.

        Args:
            key: Ключ кеша

        Returns:
            Значение кеша или None, если значение не найдено
        """
        ...

    @abstractmethod
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

    @abstractmethod
    async def delete(self, key: str) -> None:
        """
        Удалить значение из кеша.

        Args:
            key: Ключ кеша
        """
        ...

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> None:
        """
        Удалить все значения, соответствующие шаблону.

        Args:
            pattern: Шаблон ключа (например, "user_*")
        """
        ...

    async def close(self) -> None:
        """
        Закрыть соединение с хранилищем.

        Этот метод должен быть переопределен в подклассах,
        если требуется очистка ресурсов при закрытии.
        """
        pass 