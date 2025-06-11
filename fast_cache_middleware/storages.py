import typing as tp

from starlette.requests import Request
from starlette.responses import Response
from typing_extensions import TypeAlias

from .serializers import BaseSerializer, JSONSerializer, Metadata

# Определяем тип для хранимого ответа
StoredResponse: TypeAlias = tp.Tuple[Response, Request, Metadata]


# Определяем базовый класс для хранилища кэша
class BaseStorage:
    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[tp.Union[int, float]] = None,
    ) -> None:
        self._serializer = serializer or JSONSerializer()
        self._ttl = ttl

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        raise NotImplementedError()

    async def retrieve(self, key: str) -> tp.Optional[StoredResponse]:
        raise NotImplementedError()

    async def remove(self, path: str) -> None:
        raise NotImplementedError()

    async def close(self) -> None:
        raise NotImplementedError()


class InMemoryStorage(BaseStorage):
    """Хранилище кэша в памяти.

    Реализует простое хранение кэшированных ответов в словаре в памяти процесса.
    Поддерживает TTL для автоматического удаления устаревших записей.

    Args:
        serializer: Сериализатор для преобразования Response/Request в строку/байты
        ttl: Время жизни кэша в секундах. None для бессрочного хранения
    """

    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[tp.Union[int, float]] = None,
    ) -> None:
        super().__init__(serializer=serializer, ttl=ttl)
        self._storage: tp.Dict[str, StoredResponse] = {}

    async def store(
        self, key: str, response: Response, request: Request, metadata: Metadata
    ) -> None:
        """Сохраняет ответ в кэш.

        Args:
            key: Ключ для сохранения
            response: HTTP ответ для кэширования
            request: Исходный HTTP запрос
            metadata: Метаданные кэша
        """
        self._storage[key] = response, request, metadata

    async def retrieve(self, key: str) -> tp.Optional[StoredResponse]:
        """Получает ответ из кэша.

        Args:
            key: Ключ для поиска

        Returns:
            Кортеж (response, request, metadata) если найден, None если не найден
        """
        if key not in self._storage:
            return None

        return self._storage[key]

    async def remove(self, path: str) -> None:
        """Удаляет ответ из кэша по пути в запросе."""
        # Находим все ключи, соответствующие пути
        keys_to_remove = []
        for key, (_, request, _) in self._storage.items():
            if request.url.path.startswith(path):
                keys_to_remove.append(key)

        # Удаляем найденные ключи
        for key in keys_to_remove:
            del self._storage[key]

    async def close(self) -> None:
        """Очищает хранилище."""
        self._storage.clear()
