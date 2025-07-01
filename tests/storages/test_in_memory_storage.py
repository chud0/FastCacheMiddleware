"""Тесты для хранилищ кэша."""

import asyncio
import re
import time
import typing as tp

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.serializers import Metadata
from fast_cache_middleware.storages import InMemoryStorage
from fast_cache_middleware.exceptions import StorageError


@pytest.mark.parametrize(
    "max_size, ttl, expected_error",
    [
        (1000, 60.0, None),
        (500, 60.0, None),
        (0, 60.0, StorageError),
        (1000, -1, StorageError),
    ],
)
def test_initialization_params(
    max_size: int, ttl: float, expected_error: tp.Type[StorageError] | None
) -> None:
    """Тестирует параметры инициализации InMemoryStorage."""
    if expected_error is None:
        storage = InMemoryStorage(max_size=max_size, ttl=ttl)
        assert storage._max_size == max_size
        assert storage._ttl == ttl
    else:
        with pytest.raises(expected_error):
            InMemoryStorage(max_size=max_size, ttl=ttl)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl, wait_time, should_expire",
    [
        (0.1, 0.15, True),  # Должен истечь
        (1.0, 0.5, False),  # Не должен истечь
        (None, 1.0, False),  # Без TTL не истекает
    ],
)
async def test_store_and_retrieve_with_ttl(
    ttl: tp.Optional[float], wait_time: float, should_expire: bool
) -> None:
    """Тестирует сохранение и получение с TTL."""
    storage = InMemoryStorage(ttl=ttl)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    await storage.store("test_key", response, request, metadata)

    if should_expire:
        await asyncio.sleep(wait_time)

    result = await storage.retrieve("test_key")

    if should_expire:
        assert result is None
    else:
        assert result is not None
        stored_response, _, stored_metadata = result
        assert stored_response.body == b"test"
        assert stored_response.status_code == 200
        assert stored_metadata["key"] == "value"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl, cleanup_interval, wait_time, expected_cleanup_calls",
    [
        (0.1, 0.05, 0.15, 1),  # Должен вызвать очистку
        (1.0, 0.05, 0.15, 0),  # Не должен вызывать очистку
        (0.1, 0.2, 0.15, 1),  # Интервал очистки больше времени ожидания
    ],
)
async def test_expired_items_cleanup(
    ttl: float, cleanup_interval: float, wait_time: float, expected_cleanup_calls: int
) -> None:
    """Тестирует автоматическую очистку истёкших элементов."""
    storage = InMemoryStorage(max_size=10, ttl=ttl)
    storage._expiry_check_interval = cleanup_interval

    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Добавляем элемент
    await storage.store("test_key", response, request, metadata)

    # Ждем
    await asyncio.sleep(wait_time)

    # Добавляем еще один элемент, который может вызвать очистку
    await storage.store("test_key2", response, request, metadata)

    # Проверяем результат
    result = await storage.retrieve("test_key")
    if expected_cleanup_calls > 0:
        assert result is None  # Элемент должен быть удален
    else:
        assert result is not None  # Элемент должен остаться


@pytest.mark.parametrize(
    "max_size, cleanup_batch_size, cleanup_threshold",
    [
        (3, 1, 4),  # Меньшие значения
        (100, 10, 105),  # Стандартные значения
        (1000, 100, 1050),  # Большие значения
    ],
)
def test_cleanup_parameters_calculation(
    max_size: int, cleanup_batch_size: int, cleanup_threshold: int
) -> None:
    """Тестирует расчет параметров очистки."""
    storage = InMemoryStorage(max_size=max_size, ttl=None)

    assert storage._cleanup_batch_size == cleanup_batch_size
    assert storage._cleanup_threshold == cleanup_threshold
    assert storage._max_size == max_size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "max_size, num_items, expected_final_size",
    [
        (5, 3, 3),  # Просто сторит 3 элемента
        (3, 5, 4),  # Трешхолд 4, удаляем по 1 элементу,
        # поэтому после вставки пятого очистка прошла но осталось 4 элемента
        (100, 105, 105),  # Трешхолд 105, еще не превышен
        (100, 106, 100),  # Вот теперь перешагнули и удалилось батчем 6 элементов
    ],
)
async def test_lru_eviction(
    max_size: int, num_items: int, expected_final_size: int
) -> None:
    """Тестирует LRU выселение при превышении лимита."""
    storage = InMemoryStorage(max_size=max_size, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Добавляем элементы
    for i in range(num_items):
        await storage.store(f"key_{i}", response, request, metadata)

    # Проверяем размер
    assert len(storage) == expected_final_size

    # Проверяем, что последние добавленные элементы остались
    for i in range(max(0, num_items - max_size), num_items):
        result = await storage.retrieve(f"key_{i}")
        assert result is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retrive_keys, expected_keys, expire_keys",
    [
        (["first"], ["first"], []),  # Читали - остался
        (["first"], ["first"], ["second"]),  # Не читали - вытеснили
        (["first", "second"], ["first", "second"], []),  # Читали оба - остались оба
        ([], [], ["first", "second"]),  # Не читали - вылетели оба
    ],
)
async def test_retrieve_updates_lru_position(
    retrive_keys: tp.List[str],
    expected_keys: tp.List[str],
    expire_keys: tp.List[str],
    mock_store_data: tp.Tuple[Response, Request, Metadata],
) -> None:
    """Тестирует обновление позиции LRU при получении элемента."""
    keys = set(retrive_keys + expire_keys + expected_keys)
    storage = InMemoryStorage(max_size=len(keys))

    for key in keys:
        await storage.store(key, *mock_store_data)

    # Добавляем элементы чтобы заполнить хранилище и получаем то что должно остаться
    for i in range(storage._cleanup_threshold):
        await storage.store(f"key_{i}", *mock_store_data)

        for key in retrive_keys:
            await storage.retrieve(key)

    # Проверяем, какой элемент остался
    for key in expected_keys:
        assert await storage.retrieve(key) is not None

    for key in expire_keys:
        assert await storage.retrieve(key) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path_pattern, keys, expected_remaining",
    [
        (r"/api/.*", ["/api/users", "/api/posts", "/admin"], 1),  # Удаляет /api/*
        (r"/admin", ["/api/users", "/api/posts", "/admin"], 2),  # Удаляет только /admin
        (r"/nonexistent", ["/api/users", "/api/posts"], 2),  # Ничего не удаляет
    ],
)
async def test_remove_by_path_pattern(
    path_pattern: str,
    keys: tp.List[str],
    expected_remaining: int,
    mock_response: Response,
    mock_metadata: Metadata,
) -> None:
    """Тестирует удаление по паттерну пути."""
    storage = InMemoryStorage()

    # Добавляем элементы с разными путями
    for key in keys:
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": key,
                "headers": [("host", "test.com")],
            }
        )
        await storage.store(key, mock_response, request, mock_metadata)

    # Удаляем по паттерну
    pattern = re.compile(path_pattern)
    await storage.remove(pattern)

    # Проверяем количество оставшихся элементов
    assert len(storage) == expected_remaining


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key, should_exist",
    [
        ("existing_key", True),
        ("nonexistent_key", False),
    ],
)
async def test_retrieve_nonexistent_key(
    key: str, should_exist: bool, mock_store_data: tp.Tuple[Response, Request, Metadata]
) -> None:
    """Тестирует получение несуществующих ключей."""
    storage = InMemoryStorage()

    if should_exist:
        await storage.store(key, *mock_store_data)

    result = await storage.retrieve(key)

    if should_exist:
        assert result is not None
        stored_response, stored_request, stored_metadata = result
        assert stored_response.body == mock_store_data[0].body
    else:
        assert result is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "num_items, expected_size_after_close",
    [
        (0, 0),
        (5, 0),
        (10, 0),
    ],
)
async def test_close_storage(num_items: int, expected_size_after_close: int) -> None:
    """Тестирует закрытие хранилища."""
    storage = InMemoryStorage(max_size=20, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Добавляем элементы
    for i in range(num_items):
        await storage.store(f"key_{i}", response, request, metadata)

    assert len(storage) == num_items

    # Закрываем хранилище
    await storage.close()

    assert len(storage) == expected_size_after_close


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overwrite_key, expected_metadata",
    [
        (True, {"new": "value", "write_time": pytest.approx(time.time(), abs=0.1)}),
        (
            False,
            {"original": "value", "write_time": pytest.approx(time.time(), abs=0.1)},
        ),
    ],
)
async def test_store_overwrite_existing_key(
    overwrite_key: bool, expected_metadata: Metadata
) -> None:
    """Тестирует перезапись существующего ключа."""
    storage = InMemoryStorage(max_size=10, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)

    # Добавляем исходный элемент
    original_metadata = {"original": "value"}
    await storage.store("test_key", response, request, original_metadata)

    if overwrite_key:
        # Перезаписываем элемент
        new_metadata = {"new": "value"}
        await storage.store("test_key", response, request, new_metadata)

    # Получаем элемент
    result = await storage.retrieve("test_key")
    assert result is not None
    _, _, stored_metadata = result

    # Проверяем метаданные (исключая write_time, так как он динамический)
    for key, value in expected_metadata.items():
        if key != "write_time":
            assert stored_metadata[key] == value
        else:
            assert "write_time" in stored_metadata
