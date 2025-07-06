import typing as tp

import pytest
from starlette.requests import Request
from starlette.responses import Response

from fast_cache_middleware.serializers import Metadata


@pytest.fixture
def mock_request() -> Request:
    return Request(scope={"type": "http", "method": "GET", "path": "/test"})


@pytest.fixture
def mock_response() -> Response:
    return Response(content="test content", status_code=200)


@pytest.fixture
def mock_metadata() -> Metadata:
    return {"test": "value"}


@pytest.fixture
def mock_store_data(
    mock_request: Request, mock_response: Response, mock_metadata: Metadata
) -> tp.Tuple[Response, Request, Metadata]:
    return mock_response, mock_request, mock_metadata
