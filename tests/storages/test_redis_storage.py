import re
from typing import AsyncGenerator, Type
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from redis.asyncio import Redis as AsyncRedis
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
    ttl: float, expect_error: Type[BaseException] | None
) -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)

    if expect_error:
        with pytest.raises(expect_error):
            RedisStorage(redis_client=mock_redis, ttl=ttl)
    else:
        storage = RedisStorage(redis_client=mock_redis, ttl=ttl)
        assert storage._ttl == ttl
        assert isinstance(storage._serializer, JSONSerializer)


@pytest.mark.asyncio
async def test_store_and_retrieve_works() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.set = AsyncMock()
    mock_redis.get = AsyncMock()
    mock_redis.delete = AsyncMock()

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

    await storage.set("key1", response, request, metadata)
    mock_redis.set.assert_awaited_with("cache:key1", serialized_value, ex=1)

    mock_redis.get.return_value = serialized_value
    result = await storage.get("key1")

    assert result == ("deserialized_response", "req", {"meta": "data"})


@pytest.mark.asyncio
async def test_store_overwrites_existing_key() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()
    mock_redis.set = AsyncMock()

    mock_serializer = MagicMock()
    serialized_value = b"serialized"
    mock_serializer.dumps = AsyncMock(return_value=serialized_value)

    storage = RedisStorage(redis_client=mock_redis, ttl=10, serializer=mock_serializer)

    request = Request(scope={"type": "http", "method": "GET", "path": "/overwrite"})
    response = Response(content="updated", status_code=200)
    metadata: dict[str, str] = {}

    await storage.set("existing_key", response, request, metadata)

    mock_redis.delete.assert_awaited_with("cache:existing_key")
    mock_redis.set.assert_awaited_with("cache:existing_key", serialized_value, ex=10)


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_missing_key() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.exists = AsyncMock(return_value=False)
    mock_redis.get = AsyncMock(return_value=None)

    storage = RedisStorage(redis_client=mock_redis)

    with pytest.raises(TTLExpiredStorageError, match="cache:missing"):
        await storage.get("missing")


@pytest.mark.asyncio
async def test_retrieve_returns_none_on_deserialization_error() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b"invalid")
    mock_serializer = MagicMock()

    def raise_error(_):
        raise NotFoundStorageError("Data not found")

    mock_serializer.loads = raise_error
    mock_serializer.dumps = AsyncMock(return_value=b"serialized")

    storage = RedisStorage(redis_client=mock_redis, serializer=mock_serializer)

    with pytest.raises(NotFoundStorageError, match="Data not found"):
        await storage.get("missing")


@pytest.mark.asyncio
async def test_retrieve_returns_none_if_ttl_expired() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.exists = AsyncMock(return_value=True)
    mock_redis.get = AsyncMock(return_value=b"invalid")

    mock_serializer = MagicMock()

    def raise_error(_):
        raise TTLExpiredStorageError("TTL expired. Key: cache:corrupt")

    mock_serializer.loads = raise_error
    mock_serializer.dumps = AsyncMock(return_value=b"serialized")

    storage = RedisStorage(redis_client=mock_redis, serializer=mock_serializer)

    with pytest.raises(TTLExpiredStorageError, match="TTL expired"):
        await storage.get("corrupt")


@pytest.mark.asyncio
async def test_remove_by_regex() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)

    async def scan_gen() -> AsyncGenerator[str, str]:
        yield "myspace:/api/test1"
        yield "myspace:/api/test2"

    mock_redis.scan_iter = MagicMock(return_value=scan_gen())
    mock_redis.get = AsyncMock()
    mock_redis.delete = AsyncMock()

    mock_serializer = Mock()
    req1 = Mock()
    req1.url.path = "/api/test1"
    req2 = Mock()
    req2.url.path = "/api/test2"

    mock_serializer.loads = Mock(side_effect=[(None, req1, None), (None, req2, None)])
    mock_serializer.dumps = AsyncMock(
        side_effect=lambda r, resp, meta: f"{r.url.path}-serialized"
    )

    storage = RedisStorage(
        redis_client=mock_redis, serializer=mock_serializer, namespace="myspace"
    )

    pattern = re.compile(r"^/api/.*")

    await storage.delete(pattern)

    mock_redis.delete.assert_any_await("myspace:/api/test1")
    mock_redis.delete.assert_any_await("myspace:/api/test2")
    assert mock_redis.delete.await_count == 2


@pytest.mark.asyncio
async def test_remove_with_no_matches_logs_warning() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    storage = RedisStorage(redis_client=mock_redis, namespace="myspace")

    pattern = re.compile(r"^/nothing.*")

    async def empty_scan() -> AsyncGenerator[str, None]:
        if False:
            yield  # type: ignore[unreachable]
        return

    mock_redis.scan_iter = MagicMock(return_value=empty_scan())

    mock_redis.get = AsyncMock()
    mock_redis.delete = AsyncMock()

    await storage.delete(pattern)

    mock_redis.delete.assert_not_called()


@pytest.mark.asyncio
async def test_close_flushes_database() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    mock_redis.flushdb = AsyncMock()

    storage = RedisStorage(redis_client=mock_redis)

    await storage.close()
    mock_redis.flushdb.assert_awaited_once()


def test_full_key() -> None:
    mock_redis = AsyncMock(spec=AsyncRedis)
    storage = RedisStorage(redis_client=mock_redis, namespace="custom")

    assert storage._full_key("abc") == "custom:abc"
