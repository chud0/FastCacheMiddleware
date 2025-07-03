import re
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import StorageError
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
async def test_redis_storage_init_validation(ttl, expect_error):
    mock_redis = AsyncMock()

    if expect_error:
        with pytest.raises(expect_error):
            RedisStorage(redis_client=mock_redis, ttl=ttl)
    else:
        storage = RedisStorage(redis_client=mock_redis, ttl=ttl)
        assert storage._ttl == ttl
        assert isinstance(storage._serializer, JSONSerializer)


@pytest.mark.asyncio
async def test_store_and_retrieve_works():
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

    mock_redis.exists.return_value = False

    await storage.store("key1", response, request, metadata)
    mock_redis.set.assert_awaited_with("cache:key1", serialized_value, ex=1)

    mock_redis.get.return_value = serialized_value
    result = await storage.retrieve("key1")

    assert result == ("deserialized_response", "req", {"meta": "data"})


@pytest.mark.asyncio
async def test_store_overwrites_existing_key():
    mock_redis = AsyncMock()

    mock_serializer = MagicMock()
    serialized_value = b"serialized"
    mock_serializer.dumps = AsyncMock(return_value=serialized_value)

    storage = RedisStorage(redis_client=mock_redis, ttl=10, serializer=mock_serializer)

    request = Request(scope={"type": "http", "method": "GET", "path": "/overwrite"})
    response = Response(content="updated", status_code=200)
    metadata: dict[str, str] = {}

    mock_redis.exists.return_value = True

    await storage.store("existing_key", response, request, metadata)

    mock_redis.delete.assert_awaited_with("cache:existing_key")
    mock_redis.set.assert_awaited_with("cache:existing_key", serialized_value, ex=10)


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_missing_key():
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis)
    mock_redis.get.return_value = None

    result = await storage.retrieve("missing")
    assert result is None


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_deserialization_error():
    mock_redis = AsyncMock()

    def raise_error(_):
        raise ValueError("bad format")

    mock_serializer = MagicMock()
    mock_serializer.loads = raise_error

    mock_serializer.dumps = AsyncMock(return_value=b"serialized")

    storage = RedisStorage(redis_client=mock_redis, serializer=mock_serializer)

    mock_redis.get.return_value = b"invalid"

    result = await storage.retrieve("corrupt")
    assert result is None


@pytest.mark.asyncio
async def test_remove_by_regex():
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="myspace")

    pattern = re.compile(r"^/api/.*")
    mock_redis.scan.return_value = (0, ["myspace:/api/test1", "myspace:/api/test2"])

    await storage.remove(pattern)

    mock_redis.delete.assert_any_await("myspace:/api/test1")
    mock_redis.delete.assert_any_await("myspace:/api/test2")
    assert mock_redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_remove_with_no_matches_logs_warning():
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="myspace")

    pattern = re.compile(r"^/nothing.*")
    mock_redis.scan.return_value = (0, [])

    await storage.remove(pattern)
    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_close_flushes_database():
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis)

    await storage.close()
    mock_redis.flushdb.assert_awaited_once()


def test_full_key():
    mock_redis = AsyncMock()
    storage = RedisStorage(redis_client=mock_redis, namespace="custom")

    assert storage._full_key("abc") == "custom:abc"
