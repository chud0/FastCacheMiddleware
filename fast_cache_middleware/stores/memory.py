"""
In-memory реализация хранилища кеша.

Этот модуль предоставляет простую in-memory реализацию хранилища кеша
для тестирования и разработки.
"""
import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from ..core.types import CacheValue


class MemoryCacheStore:
    """
    In-memory реализация хранилища кеша.

    Эта реализация хранит данные в памяти и использует
    асинхронные блокировки для потокобезопасности.
    """

    def __init__(self) -> None:
        """Инициализация хранилища."""
        self._store: Dict[str, Tuple[CacheValue, datetime]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[CacheValue]:
        """
        Получить значение из кеша.

        Args:
            key: Ключ кеша

        Returns:
            Значение кеша или None, если значение не найдено или устарело
        """
        async with self._lock:
            if key not in self._store:
                return None

            value, expiry = self._store[key]
            if datetime.now() > expiry:
                del self._store[key]
                return None

            return value

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
        async with self._lock:
            expiry = datetime.now() + timedelta(seconds=max_age)
            self._store[key] = (value, expiry)

    async def delete(self, key: str) -> None:
        """
        Удалить значение из кеша.

        Args:
            key: Ключ кеша
        """
        async with self._lock:
            self._store.pop(key, None)

    async def delete_pattern(self, pattern: str) -> None:
        """
        Удалить все значения, соответствующие шаблону.

        Args:
            pattern: Шаблон ключа (например, "user_*")
        """
        async with self._lock:
            # Преобразуем шаблон в регулярное выражение
            regex = re.compile(pattern.replace("*", ".*"))
            keys_to_delete = [
                key for key in self._store.keys() if regex.match(key)
            ]
            for key in keys_to_delete:
                del self._store[key]

    async def clear(self) -> None:
        """Очистить все значения из кеша."""
        async with self._lock:
            self._store.clear()

    async def close(self) -> None:
        """Закрыть хранилище."""
        await self.clear() 