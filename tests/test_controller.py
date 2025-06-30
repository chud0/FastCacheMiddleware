"""Тесты для контроллера кеширования."""

import typing as tp
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.controller import Controller
from fast_cache_middleware.schemas import CacheConfiguration, RouteInfo
from fast_cache_middleware.storages import BaseStorage


@pytest.fixture
def mock_request() -> Request:
    """Создает мок HTTP запроса."""
    return Request(scope={"type": "http", "method": "GET", "path": "/test"})


@pytest.fixture
def mock_response() -> Response:
    """Создает мок HTTP ответа."""
    return Response(content="test content", status_code=200)


@pytest.fixture
def mock_storage() -> MagicMock:
    """Создает мок хранилища кеша."""
    storage = MagicMock(spec=BaseStorage)
    storage.retrieve = AsyncMock()
    storage.store = AsyncMock()
    storage.remove = AsyncMock()
    return storage


@pytest.fixture
def controller() -> Controller:
    """Создает экземпляр контроллера."""
    return Controller()


@pytest.fixture
def cache_config() -> CacheConfiguration:
    """Создает конфигурацию кеширования."""
    return CacheConfiguration(max_age=600)


@pytest.fixture
def route_info(cache_config: CacheConfiguration) -> RouteInfo:
    """Создает информацию о роуте."""
    route = MagicMock()
    return RouteInfo(route=route, cache_config=cache_config)


class TestShouldCacheRequest:
    """
    Тесты для определения необходимости кеширования запроса,
    с параметрами контроллера по умолчанию."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "method, cache_control, expected_result",
        [
            ("GET", "", True),
            ("POST", "", False),
            ("PUT", "", False),
            ("DELETE", "", False),
            (
                "GET",
                "no-cache",
                False,
            ),  # Cache-Control: no-cache
            (
                "GET",
                "no-store",
                False,
            ),  # Cache-Control: no-store
            (
                "GET",
                "max-age=3600",
                True,
            ),  # Другой Cache-Control
        ],
    )
    async def test_should_cache_request(
        self,
        method: str,
        cache_control: str,
        expected_result: bool,
        controller: Controller,
    ) -> None:
        """Тестирует определение необходимости кеширования запроса."""
        scope: tp.Dict[str, tp.Any] = {
            "type": "http",
            "method": method,
            "path": "/test",
            "headers": [],
        }
        if cache_control:
            scope["headers"] = [(b"cache-control", cache_control.encode())]

        request = Request(scope=scope)

        result = await controller.is_cachable_request(request)
        assert result == expected_result


class TestShouldCacheResponse:
    """Тесты для определения возможности кеширования ответа,
    с параметрами контроллера по умолчанию."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status_code, cache_control, content_size, expected_result",
        [
            (200, "", 1024, True),  # Успешный ответ
            (201, "", 1024, False),  # Created
            (404, "", 1024, False),  # Ошибка
            (500, "", 1024, False),  # Серверная ошибка
            (200, "no-cache", 1024, False),  # Cache-Control: no-cache
            (200, "no-store", 1024, False),  # Cache-Control: no-store
            (200, "private", 1024, False),  # Cache-Control: private
            (200, "max-age=3600", 1024, True),  # Другой Cache-Control
            (200, "", 2 * 1024 * 1024, False),  # Слишком большой ответ (>1MB)
        ],
    )
    async def test_should_cache_response(
        self,
        status_code: int,
        cache_control: str,
        content_size: int,
        expected_result: bool,
        controller: Controller,
        mock_request: Request,
    ) -> None:
        """Тестирует определение возможности кеширования ответа."""
        content = "x" * content_size
        headers = {"cache-control": cache_control} if cache_control else {}
        response = Response(content=content, status_code=status_code, headers=headers)

        result = await controller.is_cachable_response(response)
        assert result == expected_result


class TestGetCachedResponse:
    """Тесты для получения кешированного ответа."""

    @pytest.mark.asyncio
    async def test_get_cached_response_success(
        self, controller: Controller, mock_storage: MagicMock, mock_request: Request
    ) -> None:
        """Тестирует успешное получение кешированного ответа."""
        cached_response = Response(content="cached", status_code=200)
        metadata = {
            "cached_at": datetime.now(UTC).isoformat(),
            "ttl": 300,
            "etag": "test-etag",
        }
        mock_storage.retrieve.return_value = (cached_response, mock_request, metadata)

        result = await controller.get_cached_response("test_key", mock_storage)

        assert result is not None
        assert result.body == b"cached"
        assert result.status_code == 200
        mock_storage.retrieve.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_cached_response_not_found(
        self, controller: Controller, mock_storage: MagicMock, mock_request: Request
    ) -> None:
        """Тестирует получение несуществующего кеша."""
        mock_storage.retrieve.return_value = None

        result = await controller.get_cached_response("test_key", mock_storage)

        assert result is None
        mock_storage.retrieve.assert_called_once_with("test_key")

    @pytest.mark.asyncio
    async def test_get_cached_response_expired(
        self, controller: Controller, mock_storage: MagicMock, mock_request: Request
    ) -> None:
        """Тестирует получение истекшего кеша."""
        cached_response = Response(content="cached", status_code=200)
        mock_storage.retrieve.return_value = None

        result = await controller.get_cached_response("test_key", mock_storage)

        assert result is None
        mock_storage.retrieve.assert_called_once_with("test_key")


class TestCacheResponse:
    """Тесты для сохранения ответа в кеш."""

    @pytest.mark.asyncio
    async def test_cache_response_success(
        self,
        controller: Controller,
        mock_storage: MagicMock,
        mock_request: Request,
        mock_response: Response,
    ) -> None:
        """Тестирует успешное сохранение ответа в кеш."""
        await controller.cache_response(
            "test_key", mock_request, mock_response, mock_storage, 600
        )

        mock_storage.store.assert_called_once()
        call_args = mock_storage.store.call_args
        assert call_args[0][0] == "test_key"  # key
        assert call_args[0][1] == mock_response  # response
        assert call_args[0][2] == mock_request  # request
        assert call_args[0][3]["ttl"] == 600  # metadata
