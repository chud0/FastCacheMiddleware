import logging
import re
import time
import typing as tp
from collections import OrderedDict

from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import TypeAlias

from .exceptions import StorageError
from .serializers import BaseSerializer, JSONSerializer, Metadata

logger = logging.getLogger(__name__)

# Определяем тип для хранимого ответа
StoredResponse: TypeAlias = tp.Tuple[Response, Request, Metadata]


# Определяем базовый класс для хранилища кэша
class BaseStorage:
    """Базовый класс для хранилища кэша.

    Args:
        serializer: Сериализатор для преобразования Response/Request в строку/байты
        ttl: Время жизни кэша в секундах. None для бессрочного хранения
    """

    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[tp.Union[int, float]] = None,
    ) -> None:
        self._serializer = serializer or JSONSerializer()

        if ttl is not None and ttl <= 0:
            raise StorageError("TTL must be positive")

        self._ttl = ttl

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        raise NotImplementedError()

    async def retrieve(self, key: str) -> tp.Optional[StoredResponse]:
        raise NotImplementedError()

    async def remove(self, path: re.Pattern) -> None:
        raise NotImplementedError()

    async def close(self) -> None:
        raise NotImplementedError()


class InMemoryStorage(BaseStorage):
    """Хранилище кэша в памяти с поддержкой TTL и LRU выселения.

    Реализует оптимизированное хранение кэшированных ответов в памяти с:
    - LRU (Least Recently Used) выселением элементов при превышении max_size
    - TTL (Time To Live) с ленивой проверкой при чтении
    - Батчевой очисткой для лучшей производительности

    Args:
        max_size: Максимальное количество записей в кэше
        serializer: Сериализатор не используется для InMemoryStorage
        ttl: Время жизни кэша в секундах. None для бессрочного хранения
    """

    def __init__(
        self,
        max_size: int = 1000,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[tp.Union[int, float]] = None,
    ) -> None:
        super().__init__(serializer=serializer, ttl=ttl)

        if max_size <= 0:
            raise StorageError("Max size must be positive")

        self._max_size = max_size
        # Размер батча для очистки - по умолчанию 10% от max_size, минимум 1
        self._cleanup_batch_size = max(1, max_size // 10)
        # Лимит для запуска очистки - на 5% больше max_size
        self._cleanup_threshold = max_size + max(1, max_size // 20)

        # OrderedDict для эффективного LRU
        self._storage: OrderedDict[str, StoredResponse] = OrderedDict()
        # Отдельное хранение времени истечения для быстрой проверки TTL
        self._expiry_times: tp.Dict[str, float] = {}
        self._last_expiry_check_time: float = 0
        self._expiry_check_interval: float = 60

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        """Сохраняет ответ в кэш с поддержкой TTL и LRU выселения.

        Если элемент уже существует, он перемещается в конец (most recently used).
        При превышении лимита размера запускается батчевая очистка старых элементов.

        Args:
            key: Ключ для сохранения
            response: HTTP ответ для кэширования
            request: Исходный HTTP запрос
            metadata: Метаданные кэша
        """
        current_time = time.time()

        # Обновляем метаданные
        metadata = metadata.copy()
        metadata["write_time"] = current_time

        # Если элемент уже существует, удаляем его (он будет добавлен в конец)
        if key in self._storage:
            logger.info("Элемент %s удалён из кэша - перезапись", key)
            self._pop_item(key)

        self._storage[key] = (response, request, metadata)

        data_ttl = metadata.get("ttl", self._ttl)
        if data_ttl is not None:
            self._expiry_times[key] = current_time + data_ttl

        self._remove_expired_items()

        self._cleanup_lru_items()

    async def retrieve(self, key: str) -> tp.Optional[StoredResponse]:
        """Получает ответ из кэша с ленивой проверкой TTL.

        Элемент перемещается в конец для обновления LRU позиции.
        Истёкшие элементы автоматически удаляются.

        Args:
            key: Ключ для поиска

        Returns:
            Кортеж (response, request, metadata) если найден и не истёк, None если не найден или истёк
        """
        if key not in self._storage:
            return None

        # Ленивая проверка TTL
        if self._is_expired(key):
            self._pop_item(key)
            logger.debug("Элемент %s удалён из кэша - истёк TTL", key)
            return None

        self._storage.move_to_end(key)

        return self._storage[key]

    async def remove(self, path: re.Pattern) -> None:
        """Удаляет ответы из кэша по паттерну пути в запросе.

        Args:
            path: Регулярное выражение для сопоставления с путями запросов
        """
        # Находим все ключи, соответствующие паттерну пути
        keys_to_remove = []
        for key, (_, request, _) in self._storage.items():
            if path.match(request.url.path):
                keys_to_remove.append(key)

        # Удаляем найденные ключи
        for key in keys_to_remove:
            self._pop_item(key)

        logger.debug(
            "Удалено %d записей из кэша по паттерну %s",
            len(keys_to_remove),
            path.pattern,
        )

    async def close(self) -> None:
        """Очищает хранилище и освобождает ресурсы."""
        self._storage.clear()
        self._expiry_times.clear()
        logger.debug("Хранилище кэша очищено")

    def __len__(self) -> int:
        """Возвращает текущее количество элементов в кэше."""
        return len(self._storage)

    def _pop_item(self, key: str) -> StoredResponse | None:
        """Удаляет элемент из хранилища и времени истечения.

        Args:
            key: Ключ элемента для удаления
        """
        self._expiry_times.pop(key, None)
        return self._storage.pop(key, None)

    def _is_expired(self, key: str) -> bool:
        """Проверяет, истёк ли элемент по TTL."""
        try:
            return time.time() > self._expiry_times[key]
        except KeyError:
            return False

    def _remove_expired_items(self) -> None:
        """Удаляет все истёкшие элементы из кэша."""
        current_time = time.time()

        if current_time - self._last_expiry_check_time < self._expiry_check_interval:
            return

        self._last_expiry_check_time = current_time

        expired_keys = [
            key
            for key, expiry_time in self._expiry_times.items()
            if current_time > expiry_time
        ]
        if not expired_keys:
            return

        for key in expired_keys:
            self._pop_item(key)

        logger.debug("Удалено %d истёкших элементов из кэша", len(expired_keys))

    def _cleanup_lru_items(self) -> None:
        """Удаляет старые элементы по LRU стратегии при превышении лимита."""
        if len(self._storage) <= self._cleanup_threshold:
            return

        # Удаляем элементы батчами для лучшей производительности
        items_to_remove = min(
            self._cleanup_batch_size, len(self._storage) - self._max_size
        )

        for _ in range(items_to_remove):
            key, _ = self._storage.popitem(last=False)  # FIFO
            self._expiry_times.pop(key, None)

        logger.debug("Удалено %d элементов из кэша по LRU стратегии", items_to_remove)
