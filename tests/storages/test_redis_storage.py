import re
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import (
    NotFoundStorageError,
    StorageError,
    TTLExpiredStorageError,
)
from fast_cache_middleware.serializers import JSONSerializer
from fast_cache_middleware.storages import RedisStorage


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl, expect_error",
    [
        (60.0, None),
        (None, None),
        (-1, StorageError),
        (0, StorageError),
    ],
)
async def test_redis_storage_init_validation(
    ttl: float, expect_error: StorageError | None
) -> None:
    mock_redis = AsyncMock()

    if expect_error:
        with pytest.raises(expect_error):
            RedisStorage(redis_client=mock_redis, ttl=ttl)
    else:
        storage = RedisStorage(redis_client=mock_redis, ttl=ttl)
        assert storage._ttl == ttl
        assert isinstance(storage._serializer, JSONSerializer)


@pytest.mark.asyncio
async def test_store_and_retrieve_works() -> None:
    mock_redis = AsyncMock()

    mock_serializer = MagicMock()
    serialized_value = b"serialized"
    mock_serializer.dumps = AsyncMock(return_value=serialized_value)
    mock_serializer.loads = MagicMock(
        return_value=("deserialized_response", "req", {"meta": "data"})
    )

    storage = RedisStorage(redis_client=mock_redis, ttl=1, serializer=mock_serializer)

    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="hello", status_code=200)
    metadata: dict[str, str | int] = {}

    mock_redis.exists.return_value = True

    await storage.set("key1", response, request, metadata)
    mock_redis.set.assert_awaited_with("cache:key1", serialized_value, ex=1)

    mock_redis.get.return_value = serialized_value
    result = await storage.get("key1")

    assert result == ("deserialized_response", "req", {"meta": "data"})


@pytest.mark.asyncio
async def test_store_overwrites_existing_key() -> None:
    mock_redis = AsyncMock()

    mock_serializer = MagicMock()
    serialized_value = b"serialized"
    mock_serializer.dumps = AsyncMock(return_value=serialized_value)

    storage = RedisStorage(redis_client=mock_redis, ttl=10, serializer=mock_serializer)

    request = Request(scope={"type": "http", "method": "GET", "path": "/overwrite"})
    response = Response(content="updated", status_code=200)
    metadata: dict[str, str] = {}

    mock_redis.exists.return_value = True

    await storage.set("existing_key", response, request, metadata)

    mock_redis.delete.assert_awaited_with("cache:existing_key")
    mock_redis.set.assert_awaited_with("cache:existing_key", serialized_value, ex=10)


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_missing_key() -> None:
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis)
    mock_redis.get.return_value = None

    with pytest.raises(NotFoundStorageError, match="Data not found"):
        await storage.get("missing")


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_deserialization_error() -> None:
    mock_redis = AsyncMock()

    def raise_error(_):
        raise NotFoundStorageError("missing")

    mock_serializer = MagicMock()
    mock_serializer.loads = raise_error

    mock_serializer.dumps = AsyncMock(return_value=b"serialized")

    storage = RedisStorage(redis_client=mock_redis, serializer=mock_serializer)

    mock_redis.get.return_value = b"invalid"

    with pytest.raises(NotFoundStorageError, match="Data not found"):
        await storage.get("missing")


@pytest.mark.asyncio
async def test_retrieve_returns_none_if_ttl_expired() -> None:
    mock_redis = AsyncMock()

    def raise_error(_) -> None:
        raise TTLExpiredStorageError("corrupt")

    mock_serializer = MagicMock()
    mock_serializer.loads = raise_error

    mock_serializer.dumps = AsyncMock(return_value=b"serialized")

    storage = RedisStorage(redis_client=mock_redis, serializer=mock_serializer)

    mock_redis.get.return_value = b"invalid"

    with pytest.raises(TTLExpiredStorageError, match="TTL expired"):
        result = await storage.get("corrupt")
        print(result)


@pytest.mark.asyncio
async def test_remove_by_regex() -> None:
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="myspace")

    pattern = re.compile(r"^/api/.*")
    mock_redis.scan.return_value = (0, ["myspace:/api/test1", "myspace:/api/test2"])

    await storage.delete(pattern)

    mock_redis.delete.assert_any_await("myspace:/api/test1")
    mock_redis.delete.assert_any_await("myspace:/api/test2")
    assert mock_redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_remove_with_no_matches_logs_warning() -> None:
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="myspace")

    pattern = re.compile(r"^/nothing.*")
    mock_redis.scan.return_value = (0, [])

    await storage.delete(pattern)
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_close_flushes_database() -> None:
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis)

    await storage.close()
    mock_redis.flushdb.assert_awaited_once()


def test_full_key() -> None:
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="custom")

    assert storage._full_key("abc") == "custom:abc"
