"""Тесты для хранилищ кэша."""

import asyncio
import re
import time
import typing as tp

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.serializers import Metadata
from fast_cache_middleware.storages import InMemoryStorage, StorageError


@pytest.fixture
def mock_request() -> Request:
    return Request(scope={"type": "http", "method": "GET", "path": "/test"})


@pytest.fixture
def mock_response() -> Response:
    return Response(content="test content", status_code=200)


@pytest.fixture
def mock_store_data(
    mock_request: Request, mock_response: Response
) -> tp.Tuple[Request, Response, Metadata]:
    return mock_request, mock_response, {"test": "value"}


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
    if expected_error is None:
        storage = InMemoryStorage(max_size=max_size, ttl=ttl)
    else:
        with pytest.raises(expected_error):
            InMemoryStorage(max_size=max_size, ttl=ttl)
