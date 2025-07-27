"""Тесты для хранилищ кэша."""

import asyncio
import re
import time
import typing as tp

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.exceptions import (
    NotFoundStorageError,
    StorageError,
    TTLExpiredStorageError,
)
from fast_cache_middleware.serializers import Metadata
from fast_cache_middleware.storages import InMemoryStorage


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
    """Tests InMemoryStorage initialization parameters."""
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
        (0.1, 0.15, True),  # Must expire
        (1.0, 0.5, False),  # Must not expire
        (None, 1.0, False),  # Does not expire without TTL
    ],
)
async def test_store_and_retrieve_with_ttl(
    ttl: tp.Optional[float], wait_time: float, should_expire: bool
) -> None:
    """It tests saving and receiving with TTL."""
    storage = InMemoryStorage(ttl=ttl)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    await storage.set("test_key", response, request, metadata)

    await asyncio.sleep(wait_time)

    if should_expire:
        with pytest.raises(TTLExpiredStorageError):
            await storage.get("test_key")
    else:
        result = await storage.get("test_key")
        assert result is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl, cleanup_interval, wait_time, expected_cleanup_calls, expect_error",
    [
        (0.1, 0.05, 0.15, 1, NotFoundStorageError),  # Should trigger the cleanup
        (1.0, 0.05, 0.15, 0, None),  # Should not cause cleanup
        (  # The cleaning interval is longer than the waiting time
            0.1,
            0.2,
            0.15,
            1,
            TTLExpiredStorageError,
        ),
    ],
)
async def test_expired_items_cleanup(
    ttl: float,
    cleanup_interval: float,
    wait_time: float,
    expected_cleanup_calls: int,
    expect_error: tp.Type[BaseException] | None,
) -> None:
    """It tests the automatic cleaning of expired items."""
    storage = InMemoryStorage(max_size=10, ttl=ttl)
    storage._expiry_check_interval = cleanup_interval

    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Adding an element
    await storage.set("test_key", response, request, metadata)

    # Waiting
    await asyncio.sleep(wait_time)

    # Adding another element that can cause a cleanup
    await storage.set("test_key2", response, request, metadata)

    # Checking the result
    if expected_cleanup_calls > 0 and expect_error is not None:
        with pytest.raises(expect_error):
            result = await storage.get("test_key")
            assert result is None  # The element must be deleted
    else:
        result = await storage.get("test_key")
        assert result is not None  # The element must remain


@pytest.mark.parametrize(
    "max_size, cleanup_batch_size, cleanup_threshold",
    [
        (3, 1, 4),  # Lower values
        (100, 10, 105),  # Standard values
        (1000, 100, 1050),  # Large values
    ],
)
def test_cleanup_parameters_calculation(
    max_size: int, cleanup_batch_size: int, cleanup_threshold: int
) -> None:
    """Tests the calculation of cleaning parameters."""
    storage = InMemoryStorage(max_size=max_size, ttl=None)

    assert storage._cleanup_batch_size == cleanup_batch_size
    assert storage._cleanup_threshold == cleanup_threshold
    assert storage._max_size == max_size


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "max_size, num_items, expected_final_size",
    [
        (5, 3, 3),  # Just stores 3 items
        (3, 5, 4),  # Trash hold 4, we delete 1 element each,,
        # therefore, after inserting the fifth, the cleaning went through, but there were 4 elements left.
        (100, 105, 105),  # Threshold 105, not exceeded yet
        (
            100,
            106,
            100,
        ),  # Now 6 elements have been stepped over and removed by the batch
    ],
)
async def test_lru_eviction(
    max_size: int, num_items: int, expected_final_size: int
) -> None:
    """It tests LRU eviction when the limit is exceeded."""
    storage = InMemoryStorage(max_size=max_size, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Adding elements
    for i in range(num_items):
        await storage.set(f"key_{i}", response, request, metadata)

    # Checking the size
    assert len(storage) == expected_final_size

    # We check that the last added items remain.
    for i in range(max(0, num_items - max_size), num_items):
        result = await storage.get(f"key_{i}")
        assert result is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "retrive_keys, expected_keys, expire_keys",
    [
        (["first"], ["first"], []),  # If you read it, you stayed
        (  # If they didn 't read it , they were ousted.
            ["first"],
            ["first"],
            ["second"],
        ),
        (  # We both read it, but we both stayed
            ["first", "second"],
            ["first", "second"],
            [],
        ),
        ([], [], ["first", "second"]),  # If they didn't read it, they both flew out
    ],
)
async def test_retrieve_updates_lru_position(
    retrive_keys: tp.List[str],
    expected_keys: tp.List[str],
    expire_keys: tp.List[str],
    mock_store_data: tp.Tuple[Response, Request, Metadata],
) -> None:
    """It tests updating the LRU position when an item is received."""
    keys = set(retrive_keys + expire_keys + expected_keys)
    storage = InMemoryStorage(max_size=len(keys))

    for key in keys:
        await storage.set(key, *mock_store_data)

    # We add items to fill up the storage and get what should be left
    for i in range(storage._cleanup_threshold):
        await storage.set(f"key_{i}", *mock_store_data)

        for key in retrive_keys:
            await storage.get(key)

    # Checking which element is left
    for key in expected_keys:
        assert await storage.get(key) is not None

    for key in expire_keys:
        with pytest.raises(NotFoundStorageError, match="Data not found"):
            await storage.get(key)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path_pattern, keys, expected_remaining",
    [
        (r"/api/.*", ["/api/users", "/api/posts", "/admin"], 1),  # Deletes /api/*
        (r"/admin", ["/api/users", "/api/posts", "/admin"], 2),  # Deletes only /admin
        (  # It doesn't delete anything
            r"/nonexistent",
            ["/api/users", "/api/posts"],
            2,
        ),
    ],
)
async def test_remove_by_path_pattern(
    path_pattern: str,
    keys: tp.List[str],
    expected_remaining: int,
    mock_response: Response,
    mock_metadata: Metadata,
) -> None:
    """It tests deletion based on the path pattern."""
    storage = InMemoryStorage()

    # Adding elements with different paths
    for key in keys:
        request = Request(
            scope={
                "type": "http",
                "method": "GET",
                "path": key,
                "headers": [("host", "test.com")],
            }
        )
        await storage.set(key, mock_response, request, mock_metadata)

    # Deleting according to the pattern
    pattern = re.compile(path_pattern)
    await storage.delete(pattern)

    # Checking the number of remaining elements
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
    """It is testing the receipt of non-existent keys."""
    storage = InMemoryStorage()

    if should_exist:
        await storage.set(key, *mock_store_data)

    if should_exist:
        result = await storage.get(key)

        assert result is not None
        stored_response, stored_request, stored_metadata = result
        assert stored_response.body == mock_store_data[0].body
    else:
        with pytest.raises(NotFoundStorageError, match="Data not found"):
            await storage.get(key)


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
    """It is testing the closure of the storage."""
    storage = InMemoryStorage(max_size=20, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)
    metadata = {"key": "value"}

    # Adding elements
    for i in range(num_items):
        await storage.set(f"key_{i}", response, request, metadata)

    assert len(storage) == num_items

    # Closing the storage
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
    """It is testing overwriting of an existing key."""
    storage = InMemoryStorage(max_size=10, ttl=None)
    request = Request(scope={"type": "http", "method": "GET", "path": "/test"})
    response = Response(content="test", status_code=200)

    # Adding the original element
    original_metadata = {"original": "value"}
    await storage.set("test_key", response, request, original_metadata)

    if overwrite_key:
        # Overwriting the element
        new_metadata = {"new": "value"}
        await storage.set("test_key", response, request, new_metadata)

    # Getting the element
    result = await storage.get("test_key")
    assert result is not None
    _, _, stored_metadata = result

    # We check the metadata (excluding write_time, since it is dynamic)
    for key, value in expected_metadata.items():
        if key != "write_time":
            assert stored_metadata[key] == value
        else:
            assert "write_time" in stored_metadata
